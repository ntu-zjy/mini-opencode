# 第三章：LLM 通信与 SSE 流式解析

> 本章目标：理解 `llm.py` 如何与大模型 API 通信，掌握 SSE 流式响应的解析原理。

## 3.1 为什么需要手动实现 LLM 通信？

大多数项目会用 `openai` 官方 SDK：

```python
# 常见做法（本项目不用）
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...])
```

Mini-OpenCode 选择不用 SDK，而是用 `requests` 直接调用 HTTP API。这样做有三个好处：

1. **透明性**：你能看到 HTTP 请求的每一个字节
2. **零 SDK 依赖**：不需要安装 openai 包
3. **完全兼容**：任何实现了 OpenAI Chat Completions 格式的 API 都能用

## 3.2 配置层

```python
# llm.py:33-48
class Config:
    """LLM 连接配置，从环境变量读取"""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.environ.get("MODEL", "gpt-4o")

        # 确保 base_url 以 /chat/completions 结尾时直接用，否则拼接
        if self.base_url.endswith("/chat/completions"):
            self.endpoint = self.base_url
        else:
            self.endpoint = self.base_url.rstrip("/") + "/chat/completions"
```

**设计细节**：endpoint 拼接逻辑处理了两种用户输入风格：
- `https://api.openai.com/v1` → 自动拼接为 `.../v1/chat/completions`
- `https://some.api/chat/completions` → 直接使用

## 3.3 请求构造

`stream_chat()` 函数构造发送给 LLM 的请求。来看请求体的组装：

```python
# llm.py:88-106
# 1. 组装 messages
full_messages = []
for s in system:
    if s.strip():
        full_messages.append({"role": "system", "content": s})
full_messages.extend(messages)

# 2. 构建 payload
payload = {
    "model": model,
    "messages": full_messages,
    "stream": True,           # 关键：启用流式
    "temperature": temperature,
}

# 3. 如果有工具，加入工具定义
openai_tools = tool.to_openai_tools(tools) if tools else None
if openai_tools:
    payload["tools"] = openai_tools
    payload["tool_choice"] = "auto"    # LLM 自主决定是否调用工具
```

发送给 LLM API 的完整请求长这样（JSON）：

```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are an expert software engineer..."},
    {"role": "user", "content": "帮我写一个 hello.py"},
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "call_1", "content": "Wrote 3 lines..."}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "write",
        "description": "Write content to a file...",
        "parameters": {"type": "object", "properties": {...}}
      }
    }
  ],
  "tool_choice": "auto",
  "stream": true,
  "temperature": 0.7
}
```

## 3.4 重试机制

网络请求不可能百分百成功。Mini-OpenCode 实现了带指数退避的重试：

```python
# llm.py:112-162
for attempt in range(max_retries):
    try:
        resp = requests.post(
            client.endpoint,
            headers=headers,
            json=payload,
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()
        break
    except requests.exceptions.HTTPError as e:
        status = resp.status_code if resp is not None else None
        if status == 429:       # Rate Limit
            wait = 2 ** (attempt + 1)   # 指数退避: 2s, 4s, 8s
            time.sleep(wait)
            continue
        # 其他 HTTP 错误...
    except requests.exceptions.ConnectionError:
        time.sleep(3)
        continue
```

**指数退避（Exponential Backoff）** 的核心思想：

```
第 1 次重试: 等 2 秒
第 2 次重试: 等 4 秒
第 3 次重试: 等 8 秒
```

每次等待时间翻倍，避免在 API 限流时疯狂重试。

## 3.5 SSE 流式解析（核心重点）

这是本章最重要的部分。当 `stream=True` 时，LLM API 不会一次性返回完整响应，而是通过 **SSE（Server-Sent Events）** 协议逐块推送数据。

### SSE 协议格式

SSE 是一种简单的文本协议。LLM API 返回的数据流长这样：

```
data: {"id":"chatcmpl-123","choices":[{"delta":{"role":"assistant"},"index":0}]}

data: {"id":"chatcmpl-123","choices":[{"delta":{"content":"你"},"index":0}]}

data: {"id":"chatcmpl-123","choices":[{"delta":{"content":"好"},"index":0}]}

data: {"id":"chatcmpl-123","choices":[{"delta":{"content":"！"},"index":0}]}

data: {"id":"chatcmpl-123","choices":[{"finish_reason":"stop","delta":{},"index":0}]}

data: [DONE]
```

关键特征：
- 每行以 `data: ` 开头
- 每个 chunk 是一个 JSON 对象，包含一小段增量内容（`delta`）
- `[DONE]` 表示流结束
- 空行分隔不同事件

### 解析实现

```python
# llm.py:172-227
content_parts = []                          # 收集文本碎片
tool_calls_map: dict[int, dict] = {}        # 收集工具调用碎片
finish_reason = None

resp.encoding = "utf-8"
for line in resp.iter_lines(decode_unicode=True):
    if not line:
        continue
    if not line.startswith("data: "):
        continue

    data_str = line[6:]        # 去掉 "data: " 前缀
    if data_str.strip() == "[DONE]":
        break

    chunk = json.loads(data_str)
    choice = chunk["choices"][0]
    delta = choice.get("delta", {})
```

### 文本内容的增量组装

```python
    # 收集文本
    if delta.get("content"):
        print(delta["content"], end="", flush=True)  # 实时打印！
        content_parts.append(delta["content"])
```

这里的 `print(..., end="", flush=True)` 实现了"打字机效果"——每收到一个字就立刻显示，而不是等全部内容返回后再显示。`flush=True` 确保立刻刷新到终端。

### Tool Calls 的增量组装（复杂部分）

当 LLM 决定调用工具时，工具调用信息也是分块传输的。这比纯文本复杂得多：

```python
    # 收集 tool calls（需按 index 拼接参数碎片）
    if delta.get("tool_calls"):
        for tc in delta["tool_calls"]:
            idx = tc.get("index", 0)
            if idx not in tool_calls_map:
                tool_calls_map[idx] = {
                    "id": tc.get("id", ""),
                    "name": "",
                    "arguments": "",
                }
            if tc.get("id"):
                tool_calls_map[idx]["id"] = tc["id"]
            fn = tc.get("function", {})
            if fn.get("name"):
                tool_calls_map[idx]["name"] = fn["name"]
            if fn.get("arguments"):
                tool_calls_map[idx]["arguments"] += fn["arguments"]
```

**为什么工具调用参数是碎片化的？**

因为 `arguments` 是一个 JSON 字符串（可能很长），API 会把它拆成多个 chunk 发送：

```
Chunk 1: {"tool_calls": [{"index": 0, "id": "call_abc", "function": {"name": "write"}}]}
Chunk 2: {"tool_calls": [{"index": 0, "function": {"arguments": "{\"file_"}}]}
Chunk 3: {"tool_calls": [{"index": 0, "function": {"arguments": "path\": "}}]}
Chunk 4: {"tool_calls": [{"index": 0, "function": {"arguments": "\"hello.py"}}]}
Chunk 5: {"tool_calls": [{"index": 0, "function": {"arguments": "\"}"}}]}
```

代码用 `tool_calls_map[idx]["arguments"] += fn["arguments"]` 把碎片拼接成完整的 JSON 字符串。`index` 字段用于区分多个并行的工具调用。

### 最终组装

```python
# llm.py:231-255
content = "".join(content_parts) if content_parts else None

tool_calls = None
if tool_calls_map:
    tool_calls = []
    for idx in sorted(tool_calls_map.keys()):
        tc = tool_calls_map[idx]
        tool_calls.append({
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": tc["arguments"],
            },
        })

return {
    "role": "assistant",
    "content": content,
    "tool_calls": tool_calls,
    "finish_reason": finish_reason,
}
```

最终返回一个标准的 OpenAI assistant message，可以直接追加到 `session.messages` 中。

## 3.6 非流式调用

除了流式调用，`llm.py` 还提供了一个简单的非流式接口：

```python
# llm.py:261-313
def chat(client, model, system, user, max_retries=3) -> str | None:
    """非流式调用，用于简单的单轮请求"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
    }
    resp = requests.post(client.endpoint, headers=headers, json=payload, timeout=120)
    data = resp.json()
    return data["choices"][0]["message"]["content"]
```

这个接口用于不需要流式输出的简单场景（如生成会话标题、摘要等）。对比两种模式：

| | 流式 (`stream_chat`) | 非流式 (`chat`) |
|---|---|---|
| 用途 | Agent Loop 主循环 | 单轮简单请求 |
| 用户体验 | 实时打字机效果 | 等待后一次性显示 |
| 支持 tool_calls | 是 | 否 |
| 复杂度 | 高（需要 SSE 解析） | 低 |

## 3.7 流式解析的状态机模型

如果把 SSE 解析想象成一个状态机：

```
                  ┌──────────────────────────┐
                  │     等待数据 (IDLE)       │
                  └────────────┬─────────────┘
                               │ 收到 "data: ..."
                               ▼
                  ┌──────────────────────────┐
                  │     解析 JSON chunk       │
                  └────────────┬─────────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
         有 content?    有 tool_calls?   有 finish_reason?
                │              │              │
                ▼              ▼              ▼
         追加到          按 index          记录
         content_parts   拼接参数          原因
                │              │              │
                └──────────────┼──────────────┘
                               │
                        收到 "[DONE]"?
                        ┌──────┴──────┐
                        │ NO          │ YES
                        ▼             ▼
                   继续等待        组装最终结果
                                  返回 dict
```

## 3.8 常见问题与陷阱

### 中文乱码

```python
# llm.py:26-27
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# llm.py:178
resp.encoding = "utf-8"
```

两处 UTF-8 设置：一处确保 stdout 输出不乱码，一处确保 HTTP 响应解码不乱码。

### JSON 解析失败

```python
try:
    chunk = json.loads(data_str)
except json.JSONDecodeError:
    continue    # 静默跳过无法解析的行
```

某些 API 可能在流中插入非 JSON 的行（如注释或心跳），`continue` 确保不会中断整个解析。

### 空 delta

有时 chunk 中的 delta 是空的 `{}`（通常出现在流开始或结束时），所有字段的 `.get()` 调用确保了安全处理。

## 3.9 思考题

1. **为什么 tool_calls 用 `index` 而不是 `id` 来索引碎片？**
   > 提示：同一个 tool call 的 `id` 只在第一个 chunk 中出现。

2. **如果网络在 SSE 传输中断了怎么办？当前实现会发生什么？如何改进？**
   > 提示：考虑 `iter_lines()` 的异常处理。

3. **`tool_choice: "auto"` 和 `tool_choice: "required"` 有什么区别？什么场景下应该用后者？**
   > 提示：想想 Agent Loop 最后一步禁用工具的逻辑。

**下一章**：[04-tool-system.md](04-tool-system.md) —— 深入工具框架的设计，理解 Function Calling 的实现。
