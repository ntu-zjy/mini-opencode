"""
Session 与核心 Agent Loop —— 对应 OpenCode 的 src/session/prompt.ts

这是整个项目的心脏。

核心循环：
  1. 加载消息
  2. 组装 system prompt + 工具
  3. 调用 LLM
  4. 处理 tool calls → 执行工具 → 把结果追加到消息
  5. 如果 finish_reason == "tool_calls" → 继续循环
  6. 否则退出
"""

from __future__ import annotations
import json
import uuid
import os

import tool
import agent as agent_mod
import llm
import system_prompt


class Session:
    """一个会话实例"""

    def __init__(self, session_id: str | None = None, parent_id: str | None = None):
        self.id = session_id or str(uuid.uuid4())[:8]
        self.parent_id = parent_id
        self.messages: list[dict] = []  # OpenAI 格式的消息列表
        self.title = ""

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, msg: dict):
        """添加 assistant 消息（可能包含 tool_calls）"""
        entry = {"role": "assistant"}
        if msg.get("content"):
            entry["content"] = msg["content"]
        if msg.get("tool_calls"):
            entry["tool_calls"] = msg["tool_calls"]
        # OpenAI 要求 assistant message 有 content 或 tool_calls
        if "content" not in entry and "tool_calls" not in entry:
            entry["content"] = ""
        self.messages.append(entry)

    def add_tool_result(self, call_id: str, name: str, result: str):
        """添加工具执行结果"""
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": result,
            }
        )


# ── 会话存储 ──────────────────────────────────────────

_sessions: dict[str, Session] = {}


def create(parent_id: str | None = None) -> Session:
    s = Session(parent_id=parent_id)
    _sessions[s.id] = s
    return s


def get(session_id: str) -> Session | None:
    return _sessions.get(session_id)


# ── 核心循环 ──────────────────────────────────────────


async def loop(
    session: Session,
    agent: agent_mod.Agent,
    client: llm.Config,
    model: str,
    on_tool_call=None,
) -> str:
    """
    核心 Agent Loop。对应 OpenCode 的 SessionPrompt.loop()。

    while True:
      1. 组装 system prompt
      2. 按 agent 权限过滤工具
      3. 调用 LLM（流式）
      4. 如果有 tool_calls → 执行每个工具 → 追加结果 → 继续
      5. 如果没有 tool_calls → 退出，返回最终文本

    参数:
      session:  会话实例
      agent:    当前 agent 配置
      client:   OpenAI 客户端
      model:    模型名称
      on_tool_call: 工具调用时的回调（用于 UI 显示）

    返回: 最终的 assistant 文本
    """
    step = 0
    last_text = ""

    while step < agent.steps:
        step += 1

        # ── 1. 组装 system prompt ──
        system = system_prompt.build(agent)

        # ── 2. 过滤工具 ──
        tools = tool.resolve(agent.permissions)

        # 最后一步禁用工具，强制文本输出
        if step >= agent.steps:
            print(f"\n[max steps ({agent.steps}) reached, forcing text response]")
            tools = {}

        # ── 3. 调用 LLM ──
        print(f"\n{'─' * 40}")
        print(f"[step {step}/{agent.steps}] agent={agent.name} model={model}")
        print(f"[messages: {len(session.messages)}, tools: {len(tools)}]")
        print(f"{'─' * 40}")

        response = llm.stream_chat(
            client=client,
            model=model,
            system=system,
            messages=session.messages,
            tools=tools,
        )

        # ── 4. 处理响应 ──
        session.add_assistant_message(response)

        if response.get("content"):
            last_text = response["content"]

        # 如果没有 tool calls → 退出
        if not response.get("tool_calls"):
            break

        # ── 5. 执行工具 ──
        for tc in response["tool_calls"]:
            fn = tc["function"]
            name = fn["name"]
            call_id = tc["id"]

            # 解析参数
            try:
                args = json.loads(fn["arguments"])
            except json.JSONDecodeError:
                args = {}

            print(f"\n  ◆ tool: {name}")
            for k, v in args.items():
                display = str(v)[:80]
                print(f"    {k}: {display}")

            if on_tool_call:
                on_tool_call(name, args)

            # 查找并执行工具
            t = tool.get(name)
            if t:
                ctx = tool.ToolContext(
                    session_id=session.id,
                    agent_name=agent.name,
                )
                try:
                    result = await t.execute(args, ctx)
                except Exception as e:
                    result = f"Error executing tool: {e}"
            else:
                result = f"Error: Unknown tool '{name}'"

            # 显示结果摘要
            preview = result[:200].replace("\n", "\\n")
            print(f"    → {preview}{'...' if len(result) > 200 else ''}")

            # 追加工具结果到消息
            session.add_tool_result(call_id, name, result)

    return last_text
