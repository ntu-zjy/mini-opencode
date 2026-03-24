"""
System Prompt 组装 —— 对应 OpenCode 的 src/session/system.ts

组装顺序（对应 OpenCode 的 llm.ts）：
1. Agent prompt（自定义 system prompt）
2. 环境信息（工作目录、平台、日期）
3. 自定义规则（AGENTS.md）
"""

from __future__ import annotations
import os
import platform
from datetime import datetime

import agent as agent_mod

# ── 基础 prompt ────────────────────────────────────────

BASE_PROMPT = """\
You are an AI coding assistant. You help users with software engineering tasks.

## Tone and style
- Be concise and direct. Output is displayed in a terminal.
- Use markdown formatting.
- Only use emojis if the user explicitly requests it.

## Tool usage
- Use tools to complete tasks. Prefer specialized tools over bash when possible.
- Use read to read files, edit to modify files, write to create files.
- Use grep to search file contents, glob to find files by pattern.
- Use bash for shell commands that need execution.

## Task execution
- Think step by step before acting.
- Read relevant files before making changes.
- Verify changes work after making them.
"""


def build(ag: agent_mod.Agent) -> list[str]:
    """
    组装完整的 system prompt。对应 OpenCode 的 llm.ts 中的 system 组装。

    返回 list[str]，每个元素是一段 system content。
    """
    parts = []

    # 1. Agent prompt 或 base prompt
    if ag.prompt:
        parts.append(ag.prompt + "\n\n" + BASE_PROMPT)
    else:
        parts.append(BASE_PROMPT)

    # 2. 环境信息
    env = _environment()
    parts[0] += "\n\n" + env

    # 3. 自定义规则（AGENTS.md）
    rules = _custom_rules()
    if rules:
        parts[0] += "\n\n" + rules

    return parts


def _environment() -> str:
    """对应 OpenCode 的 SystemPrompt.environment()"""
    cwd = os.getcwd()
    is_git = os.path.isdir(os.path.join(cwd, ".git"))
    today = datetime.now().strftime("%a %b %d %Y")

    return f"""\
<env>
  Working directory: {cwd}
  Is directory a git repo: {"yes" if is_git else "no"}
  Platform: {platform.system().lower()}
  Today's date: {today}
</env>"""


def _custom_rules() -> str:
    """
    加载自定义规则文件。对应 OpenCode 的 SystemPrompt.custom()。
    搜索 AGENTS.md 文件。
    """
    cwd = os.getcwd()
    candidates = [
        os.path.join(cwd, "AGENTS.md"),
        os.path.join(cwd, ".opencode", "AGENTS.md"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r") as f:
                content = f.read()
            return f"Instructions from: {path}\n{content}"

    return ""
