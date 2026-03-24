# Mini-OpenCode

OpenCode 核心架构的 Python 简化复刻。约 600 行代码实现完整的 Agent Loop。

## 架构对照

| 文件               | 对应 OpenCode           | 功能                                                    |
| ------------------ | ----------------------- | ------------------------------------------------------- |
| `tool.py`          | `src/tool/tool.ts`      | 工具定义、注册、权限过滤                                |
| `builtin_tools.py` | `src/tool/bash.ts` 等   | 6 个内置工具: read/write/edit/bash/grep/glob            |
| `agent.py`         | `src/agent/agent.ts`    | Agent 定义、3 个内置 agent、权限系统                    |
| `session.py`       | `src/session/prompt.ts` | **核心 Agent Loop**: 消息管理 + LLM 调用 + 工具执行循环 |
| `llm.py`           | `src/session/llm.ts`    | OpenAI 兼容 API 流式调用（requests + SSE 手动解析）     |
| `task_tool.py`     | `src/tool/task.ts`      | **SubAgent 委派**: 创建子 Session + 递归 loop           |
| `skill.py`         | `src/skill/skill.ts`    | Skill 发现 + 加载 + SkillTool                           |
| `system_prompt.py` | `src/session/system.ts` | System Prompt 组装                                      |
| `main.py`          | `src/index.ts`          | 入口 + 简易 TUI                                         |

## 快速开始

```bash
# 安装依赖（只需 requests + pyyaml，不依赖 openai SDK）
pip install requests pyyaml

# 配置
export OPENAI_API_KEY="1963131170712068180"
export OPENAI_BASE_URL="https://aigc.sankuai.com/v1/openai/native/chat/completions"
export MODEL="glm-5"

# 运行
cd mini-opencode
python main.py
```

支持任何 OpenAI 兼容 API（DeepSeek、Ollama、vLLM 等）：

```bash
# DeepSeek
export OPENAI_API_KEY=your-deepseek-key
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export MODEL=deepseek-chat

# Ollama
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://localhost:11434/v1
export MODEL=qwen2.5:14b
```

## 使用

```
[build] > 读一下 main.py 的内容
[build] > 帮我写一个 hello world 脚本
[build] > @explore 搜索一下项目里有哪些 TODO
[build] > /agent plan
[plan]  > 分析一下这个项目的架构
```

### 命令

| 命令            | 功能             |
| --------------- | ---------------- |
| `/agent <name>` | 切换 Agent       |
| `/agents`       | 列出所有 Agent   |
| `/tools`        | 列出当前可用工具 |
| `/skills`       | 列出可用 Skill   |
| `/session`      | 显示当前会话信息 |
| `@agent 消息`   | 委派给 SubAgent  |

## 核心循环

```
用户输入 → session.loop()
             │
             ├── 1. 组装 system prompt (agent prompt + env + rules)
             ├── 2. 按权限过滤工具 (tool.resolve)
             ├── 3. 调用 LLM (llm.stream_chat)
             ├── 4. 有 tool_calls？
             │      ├── YES → 执行每个工具 → 追加结果 → 继续循环
             │      └── NO  → 退出，返回文本
             └── 5. SubAgent？ → 创建子 Session → 递归 loop()
```

## 自定义 Agent

在 `main.py` 启动前注册：

```python
import agent
agent.register(agent.Agent(
    name="reviewer",
    description="Code review specialist",
    mode="subagent",
    prompt="You are a code reviewer...",
    permissions={"*": "allow", "write": "deny", "edit": "deny"},
))
```

## 自定义 Skill

在 `skills/` 目录下创建 `<name>/SKILL.md`：

```markdown
---
name: my-skill
description: When to use this skill
---

Skill content here...
```

## 省略了什么

为了保持简洁（~600 行），省略了 OpenCode 的以下功能：

- Context compaction（上下文压缩）
- Permission ask 模式（交互式权限确认）
- Event Bus（事件驱动通信）
- SSE/REST Server（HTTP API）
- Storage 持久化（JSON 文件存储）
- Provider Transform（per-provider 消息变换）
- Anthropic Cache Control（缓存优化）
- Plugin 系统
- MCP 协议
- Git Snapshot/Revert
