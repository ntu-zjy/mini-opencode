"""
Mini-OpenCode —— OpenCode 核心架构的 Python 简化复刻

启动入口 + 简易 TUI。

运行方式:
  export OPENAI_API_KEY=your-key
  export OPENAI_BASE_URL=https://api.openai.com/v1  (可选)
  export MODEL=gpt-4o                                (可选)
  python main.py

对应 OpenCode 的 src/index.ts + src/cli/cmd/tui/app.tsx
"""

from __future__ import annotations
import asyncio
import os
import sys
import io

# ── 强制 UTF-8 输出，防止中文乱码 ──
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 初始化所有模块 ──
import tool  # 工具定义系统
import builtin_tools  # 注册内置工具 (read/write/edit/bash/grep/glob)
import agent  # Agent 定义
import skill  # Skill 系统
import task_tool  # SubAgent 委派工具
import session  # Session 与 Agent Loop
import llm  # LLM 调用层


def print_banner():
    print("""
╔══════════════════════════════════════╗
║         Mini-OpenCode v0.1          ║
║   A minimal Python clone of the     ║
║   OpenCode agent loop architecture  ║
╚══════════════════════════════════════╝
    """)


def print_help():
    print("""
Commands:
  /agent <name>    Switch agent (build, plan, explore)
  /agents          List all agents
  /tools           List available tools
  /skills          List available skills
  /session         Show current session info
  /help            Show this help
  /quit            Exit

Type your message to chat with the agent.
    """)


async def main():
    print_banner()

    # ── 配置 ──
    model = os.environ.get("MODEL", "gpt-4o")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        print("Error: Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=your-key")
        print("  export OPENAI_BASE_URL=https://api.openai.com/v1  # optional")
        print("  export MODEL=gpt-4o  # optional")
        sys.exit(1)

    print(f"Model:    {model}")
    print(f"Base URL: {base_url}")
    print(f"CWD:      {os.getcwd()}")

    # ── 初始化 ──

    # 1. 发现 Skills
    skill.discover()
    skill.register_skill_tool()

    # 2. 创建 LLM 客户端
    client = llm.create_client()

    # 3. 配置 TaskTool
    task_tool.configure(client, model)
    task_tool.register_task_tool()

    # 4. 创建初始 Session
    current_session = session.create()
    current_agent = agent.get("build")

    tools = tool.resolve(current_agent.permissions)
    print(f"Agent:    {current_agent.name}")
    print(f"Tools:    {', '.join(tools.keys())}")

    skills = skill.all_skills()
    if skills:
        print(f"Skills:   {', '.join(skills.keys())}")

    print_help()

    # ── 主循环（TUI）──
    while True:
        try:
            user_input = input(f"\n[{current_agent.name}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        # ── 命令处理 ──
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "/quit":
                print("Bye!")
                break

            elif cmd == "/help":
                print_help()

            elif cmd == "/agent":
                if not arg:
                    print(f"Current agent: {current_agent.name}")
                    print("Usage: /agent <name>")
                    continue
                a = agent.get(arg)
                if a:
                    current_agent = a
                    tools = tool.resolve(current_agent.permissions)
                    print(f"Switched to agent: {a.name} ({a.mode})")
                    print(f"Tools: {', '.join(tools.keys())}")
                else:
                    print(f"Unknown agent: {arg}")
                    print(
                        f"Available: {', '.join(a.name for a in agent.list_agents())}"
                    )

            elif cmd == "/agents":
                for a in agent.list_agents():
                    marker = "→ " if a.name == current_agent.name else "  "
                    print(f"{marker}{a.name:12} [{a.mode:8}] {a.description}")

            elif cmd == "/tools":
                tools = tool.resolve(current_agent.permissions)
                for name, t in tools.items():
                    print(f"  {name:12} {t.description[:60]}")

            elif cmd == "/skills":
                for name, s in skill.all_skills().items():
                    print(f"  {name:20} {s.description[:50]}")

            elif cmd == "/session":
                print(f"Session ID: {current_session.id}")
                print(f"Messages:   {len(current_session.messages)}")
                print(f"Parent:     {current_session.parent_id or 'none'}")

            else:
                print(f"Unknown command: {cmd}. Type /help for help.")

            continue

        # ── 对话处理 ──

        # 检查 @agent 引用（对应 OpenCode 的 resolvePromptParts）
        if user_input.startswith("@"):
            parts = user_input.split(maxsplit=1)
            agent_name = parts[0][1:]  # 去掉 @
            prompt = parts[1] if len(parts) > 1 else ""

            a = agent.get(agent_name)
            if a and a.mode != "primary":
                # 直接委派给 sub-agent
                current_session.add_user_message(
                    f"{prompt}\n\nUse the task tool to delegate this to the '{agent_name}' agent."
                )
            else:
                current_session.add_user_message(user_input)
        else:
            current_session.add_user_message(user_input)

        # 运行 Agent Loop
        result = await session.loop(
            session=current_session,
            agent=current_agent,
            client=client,
            model=model,
        )


if __name__ == "__main__":
    asyncio.run(main())
