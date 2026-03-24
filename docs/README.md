# Mini-OpenCode 教学文档

> 用 ~1500 行 Python 理解现代 AI Coding Agent 的核心架构

## 这份文档是什么？

Mini-OpenCode 是 [OpenCode](https://github.com/nicepkg/opencode) 核心架构的 Python 简化复刻。本教学文档将带你**逐模块、逐概念**地理解现代 AI 编程助手（如 Claude Code、Cursor、OpenCode）背后的工作原理。

## 阅读顺序

建议按以下顺序阅读，每章都基于前一章的概念构建：

| 章节 | 文件 | 内容 | 核心收获 |
|------|------|------|----------|
| 1 | [01-overview.md](01-overview.md) | 项目全景与架构总览 | 理解 AI Agent 的宏观架构 |
| 2 | [02-agent-loop.md](02-agent-loop.md) | 核心 Agent Loop 深度解析 | 掌握 Agent 的心脏——迭代工具调用循环 |
| 3 | [03-llm-communication.md](03-llm-communication.md) | LLM 通信与 SSE 流式解析 | 理解如何与大模型 API 交互 |
| 4 | [04-tool-system.md](04-tool-system.md) | 工具框架与内置工具 | 掌握 Function Calling 的实现原理 |
| 5 | [05-agent-design.md](05-agent-design.md) | Agent 设计与权限系统 | 学习如何设计多角色 Agent |
| 6 | [06-sub-agent.md](06-sub-agent.md) | Sub-Agent 委派与递归调用 | 理解 Agent 编排的精髓 |
| 7 | [07-skill-system.md](07-skill-system.md) | Skill 插件系统 | 学习知识注入的设计模式 |
| 8 | [08-system-prompt.md](08-system-prompt.md) | System Prompt 工程 | 掌握 Prompt 组装的最佳实践 |
| 9 | [09-hands-on.md](09-hands-on.md) | 动手练习与扩展指南 | 通过实践巩固所学 |

## 架构速览

```
                          ┌─────────────┐
                          │   main.py   │  入口 + TUI
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │ session.py  │  核心 Agent Loop ← 最重要！
                          └──────┬──────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
       ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
       │   llm.py    │   │  tool.py    │   │  agent.py   │
       │  LLM 通信   │   │  工具框架   │   │  Agent 定义  │
       └─────────────┘   └──────┬──────┘   └─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
       ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
       │builtin_tools│  │ task_tool   │  │  skill.py   │
       │  6个内置工具  │  │ SubAgent委派 │  │  Skill插件  │
       └─────────────┘  └─────────────┘  └─────────────┘
```

## 代码量统计

| 文件 | 行数 | 角色 |
|------|------|------|
| `main.py` | 202 | 入口 + TUI |
| `session.py` | 187 | 核心 Agent Loop |
| `llm.py` | 313 | LLM 通信层 |
| `tool.py` | 98 | 工具框架 |
| `builtin_tools.py` | 281 | 6 个内置工具 |
| `agent.py` | 107 | Agent 定义 |
| `task_tool.py` | 121 | SubAgent 委派 |
| `skill.py` | 129 | Skill 系统 |
| `system_prompt.py` | 98 | Prompt 组装 |
| **总计** | **~1536** | |

## 适合谁？

- 想了解 AI Coding Agent（如 Claude Code、Cursor）内部原理的开发者
- 正在构建自己的 AI Agent 的工程师
- 想学习 Function Calling / Tool Use 实现的初学者
- 对 LLM 应用架构感兴趣的技术人员

## 前置知识

- Python 基础（async/await、dataclass、type hints）
- 了解 HTTP API 的基本概念
- 对 LLM（大语言模型）有初步认识

开始阅读吧！建议从 [01-overview.md](01-overview.md) 开始。
