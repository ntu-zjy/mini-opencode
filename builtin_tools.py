"""
内置工具 —— 对应 OpenCode 的 src/tool/ 下的各个工具文件

实现: read, write, edit, bash, grep, glob, ask_user
每个工具用 tool.define() 注册
"""

from __future__ import annotations
import asyncio
import os
import subprocess
import glob as glob_mod
import re

import tool

MAX_OUTPUT = 8000  # 简化版截断，对应 OpenCode 的 Truncate.output()


def _truncate(text: str, max_len: int = MAX_OUTPUT) -> str:
    if len(text) <= max_len:
        return text
    half = max_len // 2
    removed = len(text) - max_len
    return text[:half] + f"\n\n... ({removed} chars truncated) ...\n\n" + text[-half:]


# ── read ──────────────────────────────────────────────


async def _read(params: dict, ctx: tool.ToolContext) -> str:
    path = params["file_path"]
    offset = params.get("offset", 0)
    limit = params.get("limit", 2000)

    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    if os.path.isdir(path):
        entries = os.listdir(path)
        return f"Directory listing of {path}:\n" + "\n".join(entries)

    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    selected = lines[offset : offset + limit]
    numbered = [f"{i + offset + 1:6}\t{line}" for i, line in enumerate(selected)]
    result = "".join(numbered)

    if len(lines) > offset + limit:
        result += f"\n... ({len(lines) - offset - limit} more lines)"

    return _truncate(result)


tool.define(
    name="read",
    description="Read a file from the filesystem. Returns numbered lines.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "offset": {
                "type": "integer",
                "description": "Line offset (0-based)",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Max lines to read",
                "default": 2000,
            },
        },
        "required": ["file_path"],
    },
    execute=_read,
)


# ── write ─────────────────────────────────────────────


async def _write(params: dict, ctx: tool.ToolContext) -> str:
    path = params["file_path"]
    content = params["content"]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

    lines = content.count("\n") + 1
    return f"Wrote {lines} lines to {path}"


tool.define(
    name="write",
    description="Write content to a file. Creates parent directories if needed.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to write to"},
            "content": {"type": "string", "description": "File content"},
        },
        "required": ["file_path", "content"],
    },
    execute=_write,
)


# ── edit ──────────────────────────────────────────────


async def _edit(params: dict, ctx: tool.ToolContext) -> str:
    path = params["file_path"]
    old = params["old_string"]
    new = params["new_string"]

    if not os.path.exists(path):
        return f"Error: File not found: {path}"

    with open(path, "r") as f:
        content = f.read()

    count = content.count(old)
    if count == 0:
        return "Error: old_string not found in file"
    if count > 1:
        return f"Error: old_string found {count} times. Provide more context to make it unique."

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)

    return f"Edited {path}: replaced 1 occurrence"


tool.define(
    name="edit",
    description="Replace a unique string in a file. old_string must appear exactly once.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "old_string": {"type": "string", "description": "Exact string to find"},
            "new_string": {"type": "string", "description": "Replacement string"},
        },
        "required": ["file_path", "old_string", "new_string"],
    },
    execute=_edit,
)


# ── bash ──────────────────────────────────────────────


async def _bash(params: dict, ctx: tool.ToolContext) -> str:
    command = params["command"]
    timeout = params.get("timeout", 30)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += (
                ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
            )
        if not output:
            output = "(no output)"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return _truncate(output)
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


tool.define(
    name="bash",
    description="Execute a shell command and return the output.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds",
                "default": 30,
            },
        },
        "required": ["command"],
    },
    execute=_bash,
)


# ── grep ──────────────────────────────────────────────


async def _grep(params: dict, ctx: tool.ToolContext) -> str:
    pattern = params["pattern"]
    path = params.get("path", os.getcwd())
    include = params.get("include", "")

    cmd = f'grep -rn "{pattern}" "{path}"'
    if include:
        cmd += f' --include="{include}"'
    cmd += " 2>/dev/null | head -50"

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        output = result.stdout.strip()
        return output if output else f"No matches found for '{pattern}'"
    except Exception as e:
        return f"Error: {e}"


tool.define(
    name="grep",
    description="Search file contents using regex pattern.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search"},
            "path": {"type": "string", "description": "Directory to search in"},
            "include": {
                "type": "string",
                "description": "File pattern filter, e.g. '*.py'",
            },
        },
        "required": ["pattern"],
    },
    execute=_grep,
)


# ── glob ──────────────────────────────────────────────


async def _glob(params: dict, ctx: tool.ToolContext) -> str:
    pattern = params["pattern"]
    path = params.get("path", os.getcwd())

    full_pattern = os.path.join(path, pattern)
    matches = sorted(glob_mod.glob(full_pattern, recursive=True))

    if not matches:
        return f"No files matching '{pattern}'"

    lines = matches[:100]
    result = "\n".join(lines)
    if len(matches) > 100:
        result += f"\n... and {len(matches) - 100} more"
    return result


tool.define(
    name="glob",
    description="Find files matching a glob pattern.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '**/*.py'",
            },
            "path": {"type": "string", "description": "Base directory"},
        },
        "required": ["pattern"],
    },
    execute=_glob,
)


# ── ask_user ──────────────────────────────────────────


async def _ask_user(params: dict, ctx: tool.ToolContext) -> str:
    """
    向用户提问并等待回答。
    对应 OpenCode 中 LLM 向用户确认/澄清需求的交互能力。

    这个工具比较特殊：它的 execute 需要阻塞等待用户输入。
    在 async 环境中，我们用 asyncio 在线程池中运行 input()。
    """
    question = params["question"]

    # 在终端显示问题，用可视化边框让用户注意到
    print()
    print("  ┌─ 🤖 Agent 有问题想问你 ─────────────────────")
    print(f"  │  {question}")
    print("  └─────────────────────────────────────────────")

    # input() 是阻塞调用，用 run_in_executor 避免阻塞事件循环
    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(
            None,  # 使用默认线程池
            lambda: input("  ▶ 你的回答: "),
        )
    except (EOFError, KeyboardInterrupt):
        answer = "(用户未回答)"

    print()
    return answer.strip() if answer else "(用户未回答)"


tool.define(
    name="ask_user",
    description=(
        "Ask the user a question and wait for their response. "
        "Use this when you need clarification, confirmation, or additional "
        "information from the user to proceed with a task. "
        "Examples: confirming destructive operations, choosing between options, "
        "asking for missing requirements."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user",
            },
        },
        "required": ["question"],
    },
    execute=_ask_user,
)
