"""
小红书内容创作 Agent 插件 —— Mini-OpenCode 插件示例

本插件以"零侵入"方式扩展 Mini-OpenCode，演示插件化架构：
  - 注册 1 个 primary Agent（xhs）和 4 个 SubAgent
  - 注册 4 个小红书专用工具
  - 提供 4 份 Skill 知识库（SKILL.md）

激活方式：在 main.py 中添加一行 import
  import xiaohongshu_plugin

设计隐喻：
  用户 = 甲方品牌客户
  xhs Agent = 项目总监（对接客户，统筹全局）
  xhs-planner SubAgent = 创意策划（选题、定位、竞品分析）
  xhs-copywriter SubAgent = 文案编辑（标题、正文、标签）
  xhs-image-prompt SubAgent = 视觉设计师（生成 AI 绘图提示词）
  xhs-reviewer SubAgent = 质检专员（合规审核、数据预估）
"""

from __future__ import annotations
import os

# ── 1. 注册 Agents（模块级副作用）──
from xiaohongshu_plugin import agents  # noqa: F401

# ── 2. 注册 Tools（模块级副作用）──
from xiaohongshu_plugin import tools as _xhs_tools  # noqa: F401

# ── 3. 发现 Skills ──
import skill

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
_skills_dir = os.path.join(_plugin_dir, "skills")

if os.path.isdir(_skills_dir):
    skill.discover([_skills_dir])

_skill_count = len([s for s in skill.all_skills() if s.startswith("xhs-")])
print(
    f"[xiaohongshu_plugin] Loaded: 5 agents, "
    f"{len(_xhs_tools._TOOL_NAMES)} tools, "
    f"{_skill_count} skills"
)
