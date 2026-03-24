# 第一章：项目全景与架构总览

> 本章目标：理解 AI Coding Agent 的宏观架构，建立对整个系统的全局认知。

## 1.1 什么是 AI Coding Agent？

你可能已经用过 Claude Code、Cursor、GitHub Copilot 等工具。它们看起来像是一个"会写代码的聊天机器人"，但实际上远不止于此。一个 Coding Agent 具备以下关键能力：

1. **对话**：理解自然语言指令
2. **工具调用**：能读写文件、执行命令、搜索代码
3. **迭代推理**：不断调用工具、观察结果、调整策略，直到完成任务
4. **委派**：把子任务分配给专门的 Agent 处理

这四个能力叠加在一起，就构成了现代 AI Coding Agent 的核心。Mini-OpenCode 用约 1500 行 Python 实现了这全部四个能力。

## 1.2 核心概念：Agent Loop

所有 AI Coding Agent 的核心都是同一个模式——**Agent Loop**（智能体循环）：

```
┌──────────────────────────────────────────────────────────┐
│                      Agent Loop                          │
│                                                          │
│   ┌─────────┐    ┌─────────┐    ┌──────────────────┐    │
│   │ 组装提示 │───▶│ 调用 LLM│───▶│ LLM 返回了什么？  │    │
│   └─────────┘    └─────────┘    └────────┬─────────┘    │
│        ▲                                  │              │
│        │              ┌───────────────────┼──────┐       │
│        │              │                   │      │       │
│        │         Tool Calls?          Text Only? │       │
│        │              │                   │      │       │
│        │              ▼                   ▼      │       │
│        │      ┌──────────────┐    ┌──────────┐  │       │
│        │      │  执行工具     │    │  输出结果  │  │       │
│        │      │  追加结果到   │    │  退出循环  │  │       │
│        │      │  对话历史     │    └──────────┘  │       │
│        │      └──────┬───────┘                  │       │
│        │             │                          │       │
│        └─────────────┘                          │       │
│                                                 │       │
└─────────────────────────────────────────────────────────┘
```

这就是全部了。看似简单，但这个循环的力量在于：

- LLM 可以**多轮调用工具**，逐步解决问题
- 每轮工具结果都追加到对话中，LLM 获得了"记忆"
- LLM 自主决定何时停止（当它认为任务完成时，返回纯文本而非工具调用）

## 1.3 文件结构与职责

```
mini-opencode/
├── main.py              ← 入口 + TUI（你运行的文件）
├── session.py           ← ★ 核心 Agent Loop（最重要的文件）
├── llm.py               ← 与 LLM API 的通信层
├── tool.py              ← 工具定义框架
├── builtin_tools.py     ← 6 个内置工具实现
├── agent.py             ← Agent 角色定义
├── task_tool.py         ← Sub-Agent 委派机制
├── skill.py             ← Skill 知识注入系统
├── system_prompt.py     ← System Prompt 组装
├── requirements.txt     ← 仅 2 个依赖
└── skills/
    └── example/
        └── SKILL.md     ← 示例 Skill
```

每个文件对应一个清晰的职责。这不是偶然的——它直接映射了 OpenCode 的架构：

| Mini-OpenCode 文件 | OpenCode 对应文件 | 核心职责 |
|---|---|---|
| `session.py` | `src/session/prompt.ts` | Agent Loop：消息管理 + LLM 调用 + 工具执行 |
| `llm.py` | `src/session/llm.ts` | LLM API 调用 + 流式响应解析 |
| `tool.py` | `src/tool/tool.ts` | 工具注册、权限过滤、格式转换 |
| `builtin_tools.py` | `src/tool/bash.ts` 等 | read/write/edit/bash/grep/glob |
| `agent.py` | `src/agent/agent.ts` | Agent 定义 + 权限系统 |
| `task_tool.py` | `src/tool/task.ts` | Sub-Agent 递归调用 |
| `skill.py` | `src/skill/skill.ts` | Skill 发现 + 加载 |
| `system_prompt.py` | `src/session/system.ts` | Prompt 组装 |

## 1.4 数据流：从输入到输出

当你输入一条消息时，发生了什么？

```
用户输入: "帮我写一个 hello.py"
    │
    ▼
main.py: 添加 user message 到 session
    │
    ▼
session.loop(): 进入 Agent Loop
    │
    ├── Step 1: system_prompt.build() 组装提示
    │           "You are an expert engineer..."
    │           + 环境信息 + 自定义规则
    │
    ├── Step 2: tool.resolve() 过滤可用工具
    │           build agent → [read, write, edit, bash, grep, glob, task, skill]
    │
    ├── Step 3: llm.stream_chat() 调用 LLM
    │           → LLM 返回: tool_calls: [{name: "write", args: {path: "hello.py", ...}}]
    │
    ├── Step 4: 执行 write 工具 → "Wrote 3 lines to hello.py"
    │           结果追加到 messages
    │
    ├── Step 5: 继续循环... llm.stream_chat() 再次调用
    │           → LLM 返回纯文本: "已经帮你创建了 hello.py 文件"
    │
    └── 退出循环，返回结果
```

## 1.5 技术选型：为什么这样设计？

### 为什么不用 openai SDK？

```python
# Mini-OpenCode 的做法：直接用 requests
resp = requests.post(endpoint, headers=headers, json=payload, stream=True)
for line in resp.iter_lines(decode_unicode=True):
    # 手动解析 SSE ...
```

原因：
1. **教学目的**：让你看到 LLM API 通信的每一个细节
2. **零依赖**：只需 `requests` + `pyyaml`
3. **兼容性**：任何 OpenAI 兼容 API 都能用（DeepSeek、Ollama、vLLM...）

### 为什么用全局注册表模式？

```python
# tool.py
_registry: dict[str, ToolDef] = {}

def define(name, description, parameters, execute):
    t = ToolDef(name=name, ...)
    _registry[name] = t
```

这是一种简洁有效的插件架构。工具在 import 时自注册，主程序不需要知道有哪些工具——它只需要调用 `tool.resolve()` 就能拿到所有可用工具。

### 为什么用 async？

```python
async def loop(session, agent, client, model):
    # ...
    result = await t.execute(args, ctx)
```

虽然当前的工具执行是同步的（如 subprocess.run），但 async 架构为未来扩展留了空间：并行工具调用、网络请求、MCP 协议等。

## 1.6 与真实产品的关系

Mini-OpenCode 保留了 OpenCode 的**核心骨架**，省略了**生产级细节**：

**保留了（核心架构）：**
- Agent Loop（迭代工具调用）
- Tool System（工具注册 + 权限过滤）
- Sub-Agent 委派（递归 session）
- Skill 系统（知识注入）
- 流式 SSE 解析
- System Prompt 组装

**省略了（生产细节）：**
- Context compaction（上下文太长时的压缩/摘要）
- 交互式权限确认（"允许执行 bash 命令吗？"）
- Event Bus（事件驱动架构）
- HTTP/SSE Server（作为 API 服务）
- 持久化存储（会话保存到磁盘）
- Git Snapshot/Revert（操作前保存快照）

## 1.7 本章小结

你现在应该理解了：

1. **AI Coding Agent = Agent Loop + 工具调用 + 多 Agent 协作**
2. 核心循环很简单：调用 LLM → 有工具调用就执行 → 没有就结束
3. Mini-OpenCode 用 9 个文件、~1500 行代码实现了完整架构
4. 每个文件有清晰的单一职责

**下一章**：[02-agent-loop.md](02-agent-loop.md) —— 深入 Agent Loop 的实现细节，这是整个系统最核心的部分。
