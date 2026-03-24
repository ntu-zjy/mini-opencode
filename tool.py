"""
Tool 定义系统 —— 对应 OpenCode 的 src/tool/tool.ts

核心概念：
- Tool.define(id, init) 的 Python 等价物
- 每个工具有 name, description, parameters (JSON Schema), execute
- execute 接收参数和上下文，返回字符串结果
- 工具列表在 Agent init 时根据权限过滤
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any, Awaitable


@dataclass
class ToolContext:
    """传给每个 tool.execute 的运行时上下文"""

    session_id: str
    agent_name: str
    # 简化版：不做权限检查和 abort，只保留核心


@dataclass
class ToolDef:
    """一个工具的完整定义"""

    name: str
    description: str
    parameters: dict  # JSON Schema
    execute: Callable[[dict, ToolContext], Awaitable[str]]


# ── 全局工具注册表 ──────────────────────────────────────

_registry: dict[str, ToolDef] = {}


def define(
    name: str,
    description: str,
    parameters: dict,
    execute: Callable[[dict, ToolContext], Awaitable[str]],
) -> ToolDef:
    """
    注册一个工具。对应 OpenCode 的 Tool.define()。

    参数:
      name:        工具 ID，如 "read", "bash"
      description: 描述（给 LLM 看的）
      parameters:  JSON Schema 格式的参数定义
      execute:     异步执行函数 (params, ctx) -> str
    """
    t = ToolDef(
        name=name, description=description, parameters=parameters, execute=execute
    )
    _registry[name] = t
    return t


def get(name: str) -> ToolDef | None:
    return _registry.get(name)


def all_tools() -> dict[str, ToolDef]:
    return dict(_registry)


def resolve(permissions: dict[str, str]) -> dict[str, ToolDef]:
    """
    按权限过滤工具。对应 OpenCode 的 PermissionNext.disabled()。

    permissions 格式: {"*": "allow", "bash": "deny", ...}
    规则: last-match-wins（但简化版直接用 dict 查找）
    """
    result = {}
    default = permissions.get("*", "allow")
    for name, tool in _registry.items():
        action = permissions.get(name, default)
        if action != "deny":
            result[name] = tool
    return result


def to_openai_tools(tools: dict[str, ToolDef]) -> list[dict]:
    """将工具列表转为 OpenAI function calling 格式"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools.values()
    ]
