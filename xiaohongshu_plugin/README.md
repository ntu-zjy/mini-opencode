# 小红书内容创作 Agent 插件

Mini-OpenCode 的插件化实践项目，演示如何以**零侵入方式**扩展 Agent 系统。

## 设计隐喻：外包创作团队

```
用户（甲方客户）
  │
  ▼
┌─────────────────────────────────────────────┐
│  xhs Agent（项目总监）                        │
│  - 对接客户需求，统筹全流程                     │
│  - /agent xhs 切换                           │
│                                              │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────┐│
│  │ planner │ │copywriter│ │ image-  │ │review││
│  │ 创意策划 │ │ 文案编辑  │ │ prompt  │ │ 质检 ││
│  │         │ │          │ │视觉设计  │ │      ││
│  └─────────┘ └──────────┘ └─────────┘ └──────┘│
└─────────────────────────────────────────────┘
```

## 快速开始

**唯一需要的代码改动**——在 `main.py` 的 import 区添加一行：

```python
import xiaohongshu_plugin  # 小红书内容创作插件
```

然后正常启动：

```bash
export OPENAI_API_KEY=your-key
python main.py
```

切换到小红书 Agent：

```
[build] > /agent xhs
Switched to agent: xhs (primary)
```

开始创作：

```
[xhs] > 帮我写一篇关于秋日露营的小红书笔记
```

## 组件清单

### Agents（5个）

| Agent | 类型 | 角色 | Steps |
|-------|------|------|-------|
| `xhs` | primary | 项目总监，统筹全流程 | 30 |
| `xhs-planner` | subagent | 创意策划，选题分析 | 15 |
| `xhs-copywriter` | subagent | 文案编辑，写标题正文 | 15 |
| `xhs-image-prompt` | subagent | 视觉设计，AI 配图提示词 | 12 |
| `xhs-reviewer` | subagent | 质检专员，合规审核评分 | 10 |

### Tools（4个）

| 工具 | 功能 |
|------|------|
| `xhs_tags` | 从分类标签库生成 15-20 个热门标签 |
| `xhs_format` | 格式化笔记排版 + 字数/标签数检查 |
| `xhs_review` | 4 维度质量评分（合规/质量/适配/互动） |
| `xhs_image_prompt` | 生成 MidJourney/SD 配图提示词 |

### Skills（4个 SKILL.md 知识库）

| Skill | 内容 |
|-------|------|
| `xhs-planning` | 选题公式、人群定位、竞品分析框架、内容角度矩阵 |
| `xhs-copywriting` | 标题公式、正文模板、emoji 排版、口语化技巧 |
| `xhs-image-prompt` | MidJourney/SD 提示词模板、小红书视觉审美 |
| `xhs-quality` | 社区规范、敏感词库、评分标准、数据预估模型 |

## 工作流程

当用户输入 "帮我写一篇关于露营的小红书笔记" 时：

```
1. xhs Agent 理解需求
   │
2. ├── task(xhs-planner, "分析露营主题...")
   │   └── planner 搜索趋势 + 加载 xhs-planning skill
   │       → 输出：策划方案（人群/角度/标题方向）
   │
3. ├── task(xhs-copywriter, "根据方案写文案...")
   │   └── copywriter 加载 xhs-copywriting skill + 调用 xhs_tags + xhs_format
   │       → 输出：完整文案（标题×3 + 正文 + 标签）
   │
4. ├── task(xhs-image-prompt, "根据文案生成配图提示词...")
   │   └── image-prompt 加载 xhs-image-prompt skill + 调用 xhs_image_prompt 工具
   │       → 输出：MidJourney/SD 提示词（封面图 + 内容图）
   │
5. └── task(xhs-reviewer, "审核全部内容...")
       └── reviewer 加载 xhs-quality skill + 调用 xhs_review
           → 输出：质检报告（评分 + 问题清单 + 改进建议）

6. xhs Agent 整合所有产出 → 交付给用户
```

## 插件架构原理

本插件利用 Mini-OpenCode 的 3 个全局注册表实现零侵入扩展：

```python
# agents.py  → agent.register(Agent(...))   写入 agent.AGENTS
# tools.py   → tool.define(name, ...)       写入 tool._registry
# __init__.py → skill.discover([...])       写入 skill._skills
```

**关键时序**：`import xiaohongshu_plugin` 在 `main.py` 的 import 区执行，
先于 `skill.register_skill_tool()` 和 `task_tool.register_task_tool()`。
因此插件注册的 agents 和 skills 会自动出现在这两个工具的描述中，
LLM 能看到并使用它们。

## 文件结构

```
xiaohongshu_plugin/
├── __init__.py          # 入口：import 触发所有注册
├── agents.py            # 5 个 Agent 定义
├── tools.py             # 4 个工具定义
├── README.md            # 本文件
└── skills/
    ├── xhs-planning/
    │   └── SKILL.md     # 内容策划知识库
    ├── xhs-copywriting/
    │   └── SKILL.md     # 文案写作知识库
    ├── xhs-image-prompt/
    │   └── SKILL.md     # 配图提示词知识库
    └── xhs-quality/
        └── SKILL.md     # 质检规范知识库
```
