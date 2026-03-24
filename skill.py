"""
Skill 系统 —— 对应 OpenCode 的 src/skill/skill.ts + src/tool/skill.ts

核心概念：
- Skill 是一份 SKILL.md 文件（YAML frontmatter + markdown 正文）
- LLM 调用 SkillTool 时，文件内容被注入到对话上下文
- Skill 从 ./skills/ 目录发现
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass

import tool
import yaml


@dataclass
class SkillInfo:
    name: str
    description: str
    location: str  # SKILL.md 的绝对路径
    content: str  # markdown 正文


_skills: dict[str, SkillInfo] = {}


def discover(directories: list[str] | None = None):
    """
    扫描目录中的 SKILL.md 文件。
    对应 OpenCode 的 Skill.all()。
    """
    if directories is None:
        directories = [os.path.join(os.getcwd(), "skills")]

    for base in directories:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if "SKILL.md" in files:
                path = os.path.join(root, "SKILL.md")
                _load(path)


def _load(path: str):
    """解析一个 SKILL.md 文件"""
    with open(path, "r") as f:
        raw = f.read()

    # 解析 YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        return

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return

    name = meta.get("name")
    desc = meta.get("description")
    if not name or not desc:
        return

    _skills[name] = SkillInfo(
        name=name,
        description=desc,
        location=path,
        content=match.group(2).strip(),
    )


def get(name: str) -> SkillInfo | None:
    return _skills.get(name)


def all_skills() -> dict[str, SkillInfo]:
    return dict(_skills)


# ── SkillTool ─────────────────────────────────────────


def _build_description() -> str:
    """动态构建 SkillTool 的描述，注入可用 skill 列表"""
    skills = all_skills()
    if not skills:
        return "Load a skill. No skills currently available."

    lines = [
        "Load a skill to get detailed instructions for a specific task.",
        "Skills provide specialized knowledge and step-by-step guidance.",
        "<available_skills>",
    ]
    for s in skills.values():
        lines.append(f"  <skill>")
        lines.append(f"    <name>{s.name}</name>")
        lines.append(f"    <description>{s.description}</description>")
        lines.append(f"  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


async def _skill_execute(params: dict, ctx: tool.ToolContext) -> str:
    name = params["name"]
    s = get(name)
    if not s:
        return f"Error: Skill '{name}' not found"

    base_dir = os.path.dirname(s.location)
    return f"## Skill: {s.name}\n\n**Base directory**: {base_dir}\n\n{s.content}"


def register_skill_tool():
    """注册 SkillTool。在 skill.discover() 之后调用。"""
    tool.define(
        name="skill",
        description=_build_description(),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The skill name to load"},
            },
            "required": ["name"],
        },
        execute=_skill_execute,
    )
