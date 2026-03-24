# 第六章：Sub-Agent 委派与递归调用

> 本章目标：理解 `task_tool.py` 中的 Sub-Agent 委派机制，掌握 Agent 编排的精髓。

## 6.1 什么是 Sub-Agent 委派？

假设 `build` agent 收到一个任务："分析这个项目的架构，然后重构 utils 模块"。

最佳策略是什么？

1. `build` agent 自己搜索所有文件 → 效率低，浪费步数
2. 委派搜索任务给 `explore` agent → `explore` 专注搜索，`build` 拿到结果后专注重构

这就是 Sub-Agent 委派：**一个 Agent 把子任务分配给另一个更专业的 Agent**。

## 6.2 架构：递归的力量

Sub-Agent 委派的核心是**递归调用 `session.loop()`**：

```
build agent 的 session.loop()
    │
    ├── Step 1: LLM 决定调用 task 工具
    │           args: {agent: "explore", prompt: "搜索所有 Python 文件"}
    │
    ├── Step 2: task_tool._task_execute() 被调用
    │           │
    │           ├── 创建子 Session (parent_id = 父 session.id)
    │           ├── 添加 prompt 到子 Session
    │           │
    │           └── ★ 递归调用 session.loop() ★
    │               │
    │               ├── explore agent 开始工作
    │               ├── 调用 glob, grep, read...
    │               ├── 完成后返回结果文本
    │               │
    │           ◄───┘
    │
    ├── Step 3: task 工具结果 = explore 的输出
    │           追加到 build 的消息中
    │
    └── build 继续后续工作...
```

整个过程对 `build` agent 来说，`task` 就是一个普通的工具——调用它，等结果。但在内部，一个完整的 Agent Loop 运行了一遍。

## 6.3 代码逐行解析

### 配置注入

```python
# task_tool.py:20-29
_client: llm.Config | None = None
_model: str = ""

def configure(client: llm.Config, model: str):
    """在启动时配置 client 和 model"""
    global _client, _model
    _client = client
    _model = model
```

`task_tool` 需要 LLM 的配置来创建子 Session 的通信。由于工具的 `execute` 函数签名是固定的 `(params, ctx) -> str`，无法直接传入 client。所以用模块级变量存储，在启动时注入。

### 动态描述生成

```python
# task_tool.py:32-53
def _build_description() -> str:
    """动态构建 TaskTool 的描述，注入可用 sub-agent 列表"""
    agents = agent_mod.subagents()
    if not agents:
        return "Launch a sub-agent. No sub-agents available."

    lines = [
        "Launch a new agent to handle a task autonomously.",
        "",
        "Available agent types:",
    ]
    for a in agents:
        lines.append(f"- {a.name}: {a.description}")

    lines.extend([
        "",
        "When to use: complex tasks that need specialized focus.",
        "The sub-agent runs independently and returns results.",
    ])
    return "\n".join(lines)
```

这个 description 是**动态生成的**——它会列出当前所有可用的 sub-agent。当 LLM 看到 `task` 工具的描述时，它看到的是：

```
Launch a new agent to handle a task autonomously.

Available agent types:
- explore: Fast codebase exploration agent. Good at searching and reading code.

When to use: complex tasks that need specialized focus.
The sub-agent runs independently and returns results.
```

LLM 据此知道可以用什么 agent，以及什么时候应该使用这个工具。

### 核心执行逻辑

```python
# task_tool.py:56-98
async def _task_execute(params: dict, ctx: tool.ToolContext) -> str:
    agent_name = params["agent"]
    prompt = params["prompt"]

    # 1. 解析子 agent
    sub = agent_mod.get(agent_name)
    if not sub:
        return f"Error: Agent '{agent_name}' not found"

    if not _client:
        return "Error: LLM client not configured"

    # 2. 创建子 Session
    child = session_mod.create(parent_id=ctx.session_id)
    child.add_user_message(prompt)

    # 3. 选择模型（子 agent 可绑定自己的模型）
    model = sub.model if sub.model else _model

    # 4. ★ 递归调用 loop ★
    result = await session_mod.loop(
        session=child,
        agent=sub,
        client=_client,
        model=model,
    )

    # 5. 返回结果
    return result or "(sub-agent returned no text)"
```

逐步分析：

**Step 1 - 解析 Agent**：从注册表中查找请求的 agent。如果不存在，返回错误（LLM 会在下一轮修正）。

**Step 2 - 创建子 Session**：
```python
child = session_mod.create(parent_id=ctx.session_id)
child.add_user_message(prompt)
```

子 Session 是**完全独立的**：
- 有自己的 `id`
- `parent_id` 指向父 Session（形成树状结构）
- `messages` 列表是空的（只有刚添加的 prompt）
- 不继承父 Session 的对话历史

为什么不继承？因为子 Agent 只需要完成一个特定的子任务，不需要知道父对话的全部上下文。这也减少了 token 消耗。

**Step 3 - 模型选择**：子 Agent 可以绑定自己的模型。比如，你可以让简单的搜索任务用便宜的小模型，复杂的编码任务用大模型。

**Step 4 - 递归调用**：
```python
result = await session_mod.loop(session=child, agent=sub, client=_client, model=model)
```

这是整个系统最精华的一行代码。它把同一个 `session.loop()` 函数用在了不同的上下文中：

- 不同的 Session（独立的消息历史）
- 不同的 Agent（不同的权限和 prompt）
- 可能不同的 Model

但 loop 的行为完全一样：组装提示 → 调用 LLM → 执行工具 → 循环。

**Step 5 - 返回结果**：子 Agent 的最终文本输出作为 `task` 工具的结果返回。父 Agent 会看到这个结果，然后继续自己的工作。

### 工具注册

```python
# task_tool.py:101-121
def register_task_tool():
    tool.define(
        name="task",
        description=_build_description(),
        parameters={
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "The sub-agent to use",
                },
                "prompt": {
                    "type": "string",
                    "description": "The task prompt for the sub-agent",
                },
            },
            "required": ["agent", "prompt"],
        },
        execute=_task_execute,
    )
```

`task` 工具只需要两个参数：用哪个 agent，做什么任务。简洁而强大。

## 6.4 执行流程示例

用户输入："帮我理解这个项目的架构，然后写一个 ARCHITECTURE.md"

```
[build agent]
├── Step 1: LLM 分析需求，决定先了解代码库
│   → tool_calls: [{name: "task", args: {
│       agent: "explore",
│       prompt: "分析项目结构，找到所有源文件，理解各模块的功能和依赖关系"
│     }}]
│
├── [开始执行 task 工具]
│   │
│   │  ┌── [explore agent - 子 Session]
│   │  ├── Step 1: 搜索所有 Python 文件
│   │  │   → tool_calls: [{name: "glob", args: {pattern: "**/*.py"}}]
│   │  │   → 结果: main.py, session.py, llm.py, ...
│   │  │
│   │  ├── Step 2: 读取核心文件
│   │  │   → tool_calls: [{name: "read", args: {file_path: "session.py"}}]
│   │  │   → 结果: [session.py 的内容]
│   │  │
│   │  ├── Step 3-5: 继续读取其他文件...
│   │  │
│   │  └── Step 6: 返回分析结果
│   │      → content: "项目是一个 Agent Loop 架构，包含 9 个模块..."
│   │      → task 工具结果 = 这段文本
│   │  └──
│   │
├── Step 2: build 拿到分析结果，开始写文档
│   → tool_calls: [{name: "write", args: {
│       file_path: "ARCHITECTURE.md",
│       content: "# Architecture\n\n..."
│     }}]
│
└── Step 3: 返回完成消息
    → content: "已创建 ARCHITECTURE.md 文档"
```

## 6.5 Session 树状结构

随着 Sub-Agent 的使用，Session 形成树状结构：

```
Session: abc123 (build agent)
├── messages: [user, assistant, tool, ...]
│
├── 子 Session: def456 (explore agent, parent_id=abc123)
│   └── messages: [user(prompt), assistant, tool, assistant, ...]
│
└── 子 Session: ghi789 (explore agent, parent_id=abc123)
    └── messages: [user(prompt), assistant, tool, assistant, ...]
```

每个 Session 都是独立的，只通过 `parent_id` 关联。

## 6.6 @agent 语法糖

`main.py` 提供了一个快捷方式来触发 Sub-Agent 委派：

```python
# main.py:176-188
if user_input.startswith("@"):
    parts = user_input.split(maxsplit=1)
    agent_name = parts[0][1:]      # 去掉 @
    prompt = parts[1] if len(parts) > 1 else ""

    a = agent.get(agent_name)
    if a and a.mode != "primary":
        # 注入指令，让 LLM 使用 task 工具
        current_session.add_user_message(
            f"{prompt}\n\nUse the task tool to delegate this to the '{agent_name}' agent."
        )
```

当用户输入 `@explore 搜索 TODO` 时，实际发送给 LLM 的消息是：

```
搜索 TODO

Use the task tool to delegate this to the 'explore' agent.
```

LLM 看到这个提示后，会自然地调用 `task` 工具。这是一种通过 prompt 引导工具使用的技巧。

## 6.7 递归深度与安全

当前实现中，递归委派有天然的深度限制：

1. `explore` agent 的权限中没有 `task` 工具 → 不能继续委派
2. 每个 Agent 都有 `steps` 上限 → 即使某个 Agent 卡住也会终止
3. 子 Session 是独立的 → 不会污染父 Session 的消息历史

但如果你自定义一个可以使用 `task` 的 sub-agent，理论上可以产生多层递归。实际中这不太可能失控，因为每层都有 steps 限制。

## 6.8 与 OpenCode 的对照

| 概念 | Mini-OpenCode | OpenCode |
|------|------|------|
| 入口 | `task_tool._task_execute()` | `TaskTool.execute()` |
| 子 Session | `session.create(parent_id=...)` | `SessionPrompt.create({parentId: ...})` |
| 递归调用 | `session.loop()` | `SessionPrompt.loop()` |
| Agent 过滤 | `agent.subagents()` | `AgentConfig.subagents()` |
| 模型选择 | `sub.model or _model` | `AgentConfig.model || defaultModel` |

OpenCode 额外做了：
- **并行子任务**：可以同时启动多个 sub-agent
- **结果格式化**：子 agent 的结果经过格式化处理
- **进度通知**：通过 Event Bus 通知 UI 子任务的进度

## 6.9 设计模式分析

### 模式一：组合（Composition）而非继承

Sub-Agent 不"继承"父 Agent 的能力。相反，它有自己独立的能力集合。父 Agent 通过组合（调用 task 工具）来利用子 Agent 的能力。

### 模式二：黑箱抽象

对父 Agent 来说，`task` 就是一个普通的工具。它不知道（也不需要知道）内部运行了一个完整的 Agent Loop。这种抽象让系统的复杂度可控。

### 模式三：独立的上下文

子 Session 不继承父 Session 的消息。这意味着：
- 子 Agent 只看到它的任务 prompt
- 减少了 token 消耗
- 避免了上下文污染

## 6.10 思考题

1. **子 Agent 能不能访问父 Session 的对话历史？** 当前不能。什么场景下需要这个能力？如何实现？
   > 提示：考虑子 Agent 需要理解"上下文"的场景——但也要权衡 token 消耗。

2. **如果你想实现并行的 Sub-Agent 调用（一次委派多个子任务），应该怎么改？**
   > 提示：LLM 可以在一次响应中调用多个 `task` 工具。但当前是串行执行的。

3. **Sub-Agent 的结果是纯文本。如果需要结构化数据（如 JSON）怎么办？**
   > 提示：可以在 prompt 中要求子 Agent 以特定格式输出，但需要父 Agent 解析。

**下一章**：[07-skill-system.md](07-skill-system.md) —— Skill 插件系统，理解知识注入的设计模式。
