"""
TaskTool (SubAgent 委派) —— 对应 OpenCode 的 src/tool/task.ts

核心概念：
- LLM 调用 task tool 时，创建一个子 Session
- 子 Session 用指定的 sub-agent 运行独立的 loop
- 结果回传给父 Session
- 这就是 OpenCode 最精华的 agent 递归调用
"""

from __future__ import annotations
import json

import tool
import agent as agent_mod
import session as session_mod
import llm


# 存储当前的 client 和 model（在 main 中设置）
_client: llm.Config | None = None
_model: str = ""


def configure(client: llm.Config, model: str):
    """在启动时配置 client 和 model"""
    global _client, _model
    _client = client
    _model = model


def _build_description() -> str:
    """动态构建 TaskTool 的描述，注入可用 sub-agent 列表"""
    agents = agent_mod.subagents()
    if not agents:
        return "Launch a sub-agent. No sub-agents available."

    lines = [
        "Launch a new agent to handle a task autonomously.",
        "",
        "Available agent types:",
    ]
    for a in agents:
        lines.append(f"- {a.name}: {a.description}")

    lines.extend(
        [
            "",
            "When to use: complex tasks that need specialized focus.",
            "The sub-agent runs independently and returns results.",
        ]
    )
    return "\n".join(lines)


async def _task_execute(params: dict, ctx: tool.ToolContext) -> str:
    """
    执行 SubAgent 委派。对应 OpenCode task.ts 的 execute()。

    流程：
    1. 解析子 agent
    2. 创建子 Session（parentId 指向当前 session）
    3. 递归调用 session.loop()
    4. 返回结果给父 agent
    """
    agent_name = params["agent"]
    prompt = params["prompt"]

    # 1. 解析子 agent
    sub = agent_mod.get(agent_name)
    if not sub:
        return f"Error: Agent '{agent_name}' not found"

    if not _client:
        return "Error: LLM client not configured"

    # 2. 创建子 Session
    child = session_mod.create(parent_id=ctx.session_id)
    child.add_user_message(prompt)

    print(f"\n  ┌── SubAgent: {sub.name} (session: {child.id})")
    print(f"  │  prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

    # 3. 选择模型（子 agent 可绑定自己的模型）
    model = sub.model if sub.model else _model

    # 4. 递归调用 loop —— 这就是 OpenCode 的精髓
    result = await session_mod.loop(
        session=child,
        agent=sub,
        client=_client,
        model=model,
    )

    print(f"  └── SubAgent {sub.name} completed")

    # 5. 返回结果
    return result or "(sub-agent returned no text)"


def register_task_tool():
    """注册 TaskTool。在 agent 和 tool 初始化之后调用。"""
    tool.define(
        name="task",
        description=_build_description(),
        parameters={
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "The sub-agent to use",
                },
                "prompt": {
                    "type": "string",
                    "description": "The task prompt for the sub-agent",
                },
            },
            "required": ["agent", "prompt"],
        },
        execute=_task_execute,
    )
