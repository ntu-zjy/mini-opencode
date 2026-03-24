# 第二章：核心 Agent Loop 深度解析

> 本章目标：深入理解 `session.py` 中 Agent Loop 的每一步，掌握 AI Agent 的心脏。

## 2.1 为什么 Agent Loop 是核心？

如果让你只看这个项目的一个文件，应该看 `session.py`。它只有 187 行，却定义了整个系统最关键的行为：**LLM 和工具之间的迭代交互**。

没有 Agent Loop，LLM 只是一个一问一答的聊天机器人。有了 Agent Loop，它变成了一个能自主行动、观察、再行动的智能体。

## 2.2 Session：对话的容器

在进入 Loop 之前，先理解 Session 的结构：

```python
# session.py:26-58
class Session:
    """一个会话实例"""

    def __init__(self, session_id=None, parent_id=None):
        self.id = session_id or str(uuid.uuid4())[:8]
        self.parent_id = parent_id          # 如果是子 session，记录父 ID
        self.messages: list[dict] = []      # OpenAI 格式的消息列表
        self.title = ""
```

**关键设计点：**

- `messages` 是一个 OpenAI 格式的消息列表，这是整个系统的"记忆"
- `parent_id` 支持子 Session（为 Sub-Agent 委派做准备，第六章详解）
- 消息格式遵循 OpenAI 标准：`{"role": "user/assistant/tool", "content": "..."}`

Session 提供了三个方法来管理消息：

```python
def add_user_message(self, text):
    self.messages.append({"role": "user", "content": text})

def add_assistant_message(self, msg):
    entry = {"role": "assistant"}
    if msg.get("content"):
        entry["content"] = msg["content"]
    if msg.get("tool_calls"):
        entry["tool_calls"] = msg["tool_calls"]
    self.messages.append(entry)

def add_tool_result(self, call_id, name, result):
    self.messages.append({
        "role": "tool",
        "tool_call_id": call_id,
        "content": result,
    })
```

注意 `add_tool_result` 中的 `tool_call_id`——这个字段把工具结果和对应的工具调用关联起来，是 OpenAI Function Calling 协议的一部分。

## 2.3 Agent Loop 逐行解析

现在进入核心。下面是 `loop()` 函数的完整逻辑，我会逐段讲解：

### 函数签名

```python
# session.py:79-104
async def loop(
    session: Session,
    agent: agent_mod.Agent,
    client: llm.Config,
    model: str,
    on_tool_call=None,
) -> str:
```

五个参数：
- `session`：当前对话（包含所有历史消息）
- `agent`：当前使用的 Agent（决定可用工具和系统提示）
- `client`：LLM 连接配置
- `model`：模型名称
- `on_tool_call`：可选的回调函数（用于 UI 显示工具调用）

### 循环主体

```python
    step = 0
    last_text = ""

    while step < agent.steps:    # agent.steps 是最大迭代次数
        step += 1
```

`agent.steps` 是一个安全阀：
- `build` agent: 50 步
- `plan` agent: 20 步
- `explore` agent: 30 步

没有这个限制，一个出错的 LLM 可能会无限循环下去。

### Step 1: 组装 System Prompt

```python
        # ── 1. 组装 system prompt ──
        system = system_prompt.build(agent)
```

每轮循环都重新组装 system prompt。虽然当前实现中它不会变化，但这个设计为动态 prompt 留了空间（例如根据当前步数调整指令）。详见[第八章](08-system-prompt.md)。

### Step 2: 过滤工具

```python
        # ── 2. 过滤工具 ──
        tools = tool.resolve(agent.permissions)

        # 最后一步禁用工具，强制文本输出
        if step >= agent.steps:
            print(f"\n[max steps ({agent.steps}) reached, forcing text response]")
            tools = {}
```

这里有一个精妙的设计：**当达到最大步数时，清空工具列表**。

为什么？因为如果 LLM 还有可用工具，它可能继续调用工具而不返回文本。清空工具后，LLM 被迫只能生成文本回复——这就是所谓的 "forcing a text response"。

### Step 3: 调用 LLM

```python
        # ── 3. 调用 LLM ──
        response = llm.stream_chat(
            client=client,
            model=model,
            system=system,
            messages=session.messages,
            tools=tools,
        )
```

把完整的对话历史（包括之前的工具调用和结果）发送给 LLM。LLM 的响应有两种可能：

1. **纯文本**：`{"content": "这是回复", "tool_calls": None}` → 任务完成
2. **工具调用**：`{"content": null, "tool_calls": [...]}` → 需要执行工具

### Step 4: 处理响应

```python
        # ── 4. 处理响应 ──
        session.add_assistant_message(response)

        if response.get("content"):
            last_text = response["content"]

        # 如果没有 tool calls → 退出
        if not response.get("tool_calls"):
            break
```

**关键分支点**：
- 如果 `tool_calls` 为空 → `break`，退出循环，返回文本
- 如果有 `tool_calls` → 继续到 Step 5 执行工具

### Step 5: 执行工具

```python
        # ── 5. 执行工具 ──
        for tc in response["tool_calls"]:
            fn = tc["function"]
            name = fn["name"]
            call_id = tc["id"]

            # 解析参数
            try:
                args = json.loads(fn["arguments"])
            except json.JSONDecodeError:
                args = {}
```

LLM 返回的 `tool_calls` 是一个数组——LLM 可以在一次响应中调用多个工具（并行工具调用）。每个工具调用包含：
- `id`：唯一标识符（用于关联结果）
- `function.name`：工具名称
- `function.arguments`：JSON 格式的参数字符串

```python
            # 查找并执行工具
            t = tool.get(name)
            if t:
                ctx = tool.ToolContext(
                    session_id=session.id,
                    agent_name=agent.name,
                )
                try:
                    result = await t.execute(args, ctx)
                except Exception as e:
                    result = f"Error executing tool: {e}"
            else:
                result = f"Error: Unknown tool '{name}'"

            # 追加工具结果到消息
            session.add_tool_result(call_id, name, result)
```

注意错误处理：即使工具执行失败，错误信息也会作为结果追加到消息中。这样 LLM 能看到错误，并在下一轮尝试修正（比如用不同参数重试）。

### 循环结束

```python
    return last_text
```

工具全部执行完后，循环回到 Step 1，再次调用 LLM。LLM 看到工具执行结果后，决定是否需要更多操作。

## 2.4 一个完整的执行示例

用户说："帮我创建一个计算器脚本，然后运行测试一下"

```
Step 1: LLM 决定先创建文件
  → tool_calls: [{name: "write", args: {path: "calc.py", content: "..."}}]
  → 执行 write → "Wrote 20 lines to calc.py"
  → 追加结果，继续循环

Step 2: LLM 看到文件创建成功，决定运行测试
  → tool_calls: [{name: "bash", args: {command: "python calc.py"}}]
  → 执行 bash → "2 + 3 = 5\nAll tests passed"
  → 追加结果，继续循环

Step 3: LLM 看到测试通过，任务完成
  → content: "已为你创建 calc.py，包含加减乘除功能。运行测试全部通过。"
  → tool_calls: None
  → break，退出循环
```

整个过程中，消息列表的变化：

```python
messages = [
    {"role": "user", "content": "帮我创建一个计算器脚本..."},

    # Step 1
    {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "write", ...}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "Wrote 20 lines..."},

    # Step 2
    {"role": "assistant", "tool_calls": [{"id": "call_2", "function": {"name": "bash", ...}}]},
    {"role": "tool", "tool_call_id": "call_2", "content": "2 + 3 = 5\nAll tests passed"},

    # Step 3
    {"role": "assistant", "content": "已为你创建 calc.py..."},
]
```

## 2.5 设计模式分析

### 模式一：消息即状态

Agent Loop 没有复杂的状态机。所有状态都编码在 `messages` 列表中：
- 用户说了什么 → user messages
- LLM 做了什么 → assistant messages (with tool_calls)
- 工具返回了什么 → tool messages

这意味着 LLM 的每次决策都基于完整的对话历史，不会丢失上下文。

### 模式二：退出条件的优雅设计

```python
if not response.get("tool_calls"):
    break
```

Agent Loop 的退出完全由 LLM 决定。当 LLM 认为任务完成时，它自然地生成纯文本而不是工具调用。这比硬编码退出条件优雅得多。

安全网是 `agent.steps`——即使 LLM 反复调用工具不停，也会在达到上限后被强制结束。

### 模式三：错误恢复

```python
try:
    result = await t.execute(args, ctx)
except Exception as e:
    result = f"Error executing tool: {e}"
```

工具执行的错误不会中断循环，而是被包装成文本结果反馈给 LLM。这让 LLM 有机会自我修正——比如读文件路径错误时，LLM 可能会在下一轮用 `glob` 先搜索正确路径。

## 2.6 与 OpenCode 的对照

| 概念 | Mini-OpenCode | OpenCode |
|------|------|------|
| 核心循环 | `session.loop()` | `SessionPrompt.loop()` |
| 消息存储 | `session.messages[]` | `SessionPrompt.messages[]` (持久化到 JSON) |
| 步数限制 | `agent.steps` | `AgentConfig.maxSteps` |
| 工具过滤 | `tool.resolve()` | `PermissionNext.disabled()` |
| 退出条件 | `tool_calls` 为空 | `finish_reason` + `tool_calls` 检查 |
| 错误处理 | try/except 包装 | 类似 + 更详细的错误类型 |

OpenCode 额外做了：
- **Context compaction**：当消息太多时，自动摘要压缩
- **Permission ask**：执行危险工具前询问用户
- **Event bus**：工具执行进度通过事件系统通知 UI

## 2.7 思考题

1. **为什么每轮都重新调用 `tool.resolve()`？** 在当前实现中权限不会变化，这样做有什么好处？
   > 提示：考虑动态权限场景——用户可能在某轮批准或拒绝某个工具的使用。

2. **如果 LLM 在一次响应中调用了 5 个工具，它们是串行执行的。能否改为并行？有什么风险？**
   > 提示：考虑工具之间的依赖关系（如先创建目录再写文件）。

3. **当前实现把所有消息都发送给 LLM。当对话很长时会怎样？你会怎么解决？**
   > 提示：这就是 OpenCode 做 context compaction 的原因。

**下一章**：[03-llm-communication.md](03-llm-communication.md) —— 深入 LLM 通信层，理解 SSE 流式解析的实现。
