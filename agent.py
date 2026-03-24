"""
Agent 定义系统 —— 对应 OpenCode 的 src/agent/agent.ts

核心概念：
- Agent 有 name, description, mode, prompt, model, permissions
- mode: "primary" (用户直接使用), "subagent" (被 TaskTool 调用), "all" (两者)
- permissions 控制哪些工具可用（last-match-wins 简化版）
- 内置 agent: build, plan, explore
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Agent:
    name: str
    description: str = ""
    mode: str = "all"  # "primary" | "subagent" | "all"
    prompt: str = ""  # 自定义 system prompt
    model: str = ""  # 绑定模型（空 = 用默认）
    permissions: dict = field(default_factory=lambda: {"*": "allow"})
    steps: int = 50  # 最大迭代次数


# ── 内置 Agent ────────────────────────────────────────

AGENTS: dict[str, Agent] = {}


def _register(a: Agent):
    AGENTS[a.name] = a
    return a


_register(
    Agent(
        name="build",
        description="General purpose coding agent. Can read, write, and execute code.",
        mode="primary",
        prompt="You are an expert software engineer. You help users write, debug, and improve code.",
        permissions={"*": "allow"},
        steps=50,
    )
)

_register(
    Agent(
        name="plan",
        description="Read-only planning agent. Cannot modify files.",
        mode="primary",
        prompt="You are a planning assistant. Analyze requirements and create plans. NEVER modify files.",
        permissions={
            "*": "allow",
            "write": "deny",
            "edit": "deny",
            "bash": "deny",
        },
        steps=20,
    )
)

_register(
    Agent(
        name="explore",
        description="Fast codebase exploration agent. Good at searching and reading code.",
        mode="subagent",
        prompt="You are a codebase exploration specialist. Find files, read code, answer questions.",
        permissions={
            "*": "deny",
            "read": "allow",
            "grep": "allow",
            "glob": "allow",
            "bash": "allow",
        },
        steps=30,
    )
)


def get(name: str) -> Agent | None:
    return AGENTS.get(name)


def list_agents() -> list[Agent]:
    return list(AGENTS.values())


def register(a: Agent):
    """注册自定义 Agent"""
    AGENTS[a.name] = a


def subagents(caller: Agent | None = None) -> list[Agent]:
    """
    获取可用子 agent 列表。对应 OpenCode TaskTool init 时的过滤。
    - 排除 mode == "primary"
    - 如果 caller 有权限限制，进一步过滤
    """
    result = []
    for a in AGENTS.values():
        if a.mode == "primary":
            continue
        # 简化：不做 caller 对 task 权限的检查
        if a.description:  # 没有 description 的不暴露给 LLM
            result.append(a)
    return result
