# 第九章：动手练习 —— 自定义工具开发教程

> 本章目标：通过实现 `search_web` 工具，掌握从零开发自定义工具的完整流程。

## 9.1 开始之前

在前面几章中，你已经理解了 Mini-OpenCode 的核心架构：Agent Loop、LLM 通信、工具框架。现在是动手实践的时候了。

本章以 `search_web`（网页搜索）工具为例，**手把手**带你走完自定义工具开发的全过程。这个工具让 Agent 能够搜索互联网获取实时信息——这是一个非常实用的能力。

## 9.2 自定义工具开发的三步法

添加任何自定义工具，只需要三步：

```
Step 1: 写一个 async 执行函数    (params, ctx) -> str
Step 2: 调用 tool.define() 注册   name + description + schema + execute
Step 3: 在 main.py 中 import      让模块级代码自动执行
```

就这么简单。下面我们一步步来。

## 9.3 Step 1：创建工具文件

创建 `search_web_tool.py`：

```python
# search_web_tool.py
"""
自定义工具示例：search_web —— 网页搜索工具
"""

from __future__ import annotations
import re
import requests
import tool
```

为什么要单独建文件？
- **关注点分离**：自定义工具不应该塞进 `builtin_tools.py`
- **易于管理**：一个文件一个工具（或一类工具），增删方便
- **教学清晰**：独立的文件让工具的完整结构一目了然

## 9.4 Step 2：实现搜索逻辑

先实现底层的搜索函数。我们用 DuckDuckGo 的 HTML 接口，不需要任何 API Key：

```python
def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """
    使用 DuckDuckGo HTML 搜索。无需 API Key。

    返回:
      [{"title": "...", "url": "...", "snippet": "..."}, ...]
    """
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    resp = requests.post(url, data=params, headers=headers, timeout=10)
    resp.raise_for_status()
    html = resp.text

    # 正则解析搜索结果
    results = []
    pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        r'.*?'
        r'class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        if len(results) >= max_results:
            break

        raw_url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

        # 提取真实 URL（DuckDuckGo 用重定向链接）
        real_url = raw_url
        url_match = re.search(r"uddg=([^&]+)", raw_url)
        if url_match:
            from urllib.parse import unquote
            real_url = unquote(url_match.group(1))

        if title:
            results.append({
                "title": title,
                "url": real_url,
                "snippet": snippet,
            })

    return results
```

**关键设计决策**：

1. **为什么用 DuckDuckGo？** 不需要 API Key，降低使用门槛。教学优先。
2. **为什么用正则而不是 BeautifulSoup？** 减少依赖。项目只依赖 `requests` 和 `pyyaml`。
3. **为什么要提取真实 URL？** DuckDuckGo 返回的是重定向链接 `//duckduckgo.com/l/?uddg=...`，提取真实 URL 对 LLM 更有用。

## 9.5 Step 3：实现结果格式化

工具返回给 LLM 的是一个字符串。格式很重要——好的格式让 LLM 更容易理解和引用：

```python
def _format_results(results: list[dict], query: str) -> str:
    """将搜索结果格式化为 LLM 友好的文本"""
    if not results:
        return f"No results found for '{query}'"

    lines = [f"Search results for: {query}", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   URL: {r['url']}")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
        lines.append("")

    return "\n".join(lines)
```

格式化的原则：
- **编号**：让 LLM 可以引用 "第 3 条结果"
- **Markdown 粗体**：标题突出显示
- **URL 单独一行**：方便 LLM 提取和引用
- **Snippet 缩进**：视觉层次清晰

## 9.6 Step 4：编写 execute 函数

这是工具的入口点。它必须满足 `tool.define()` 要求的签名：

```python
async def _search_web(params: dict, ctx: tool.ToolContext) -> str:
    """
    搜索网页。这是 tool.define() 需要的 execute 函数。

    签名必须是: async (params: dict, ctx: ToolContext) -> str
    """
    query = params["query"]
    max_results = params.get("max_results", 5)

    try:
        results = _search_duckduckgo(query, max_results)
        return _format_results(results, query)
    except requests.exceptions.Timeout:
        return f"Error: Search timed out for '{query}'"
    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to search service"
    except Exception as e:
        return f"Error searching for '{query}': {e}"
```

注意几个要点：

1. **`async` 函数**：所有工具的 execute 都必须是 async 的（即使内部没有 await）
2. **参数从 `params` dict 取**：对应 JSON Schema 中定义的字段
3. **返回值是字符串**：不管成功还是失败，都返回一个描述性的字符串
4. **全面的错误处理**：网络请求可能超时、断连，必须优雅处理

> **为什么错误也返回字符串而不抛异常？**
> 因为工具执行结果会被追加到对话中发给 LLM。LLM 看到错误消息后可以：
> - 换个关键词重试
> - 告诉用户搜索失败了
> - 改用其他工具获取信息
>
> 这就是 Agent Loop 的自愈能力。

## 9.7 Step 5：注册工具

最关键的一步——调用 `tool.define()` 将工具注册到全局注册表：

```python
tool.define(
    name="search_web",
    description=(
        "Search the web for information using a search engine. "
        "Returns titles, URLs, and snippets of the top results. "
        "Use this when you need up-to-date information, "
        "want to find documentation, or need to research a topic."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    execute=_search_web,
)
```

### description 的写法技巧

`description` 是给 LLM 看的 prompt。写好它直接影响 LLM 是否能在正确的时机选择使用这个工具。

好的 description 应该回答三个问题：
1. **这个工具做什么？** → "Search the web for information"
2. **输出是什么格式？** → "Returns titles, URLs, and snippets"
3. **什么时候该用它？** → "when you need up-to-date information..."

### JSON Schema 的写法

`parameters` 使用 [JSON Schema](https://json-schema.org/) 格式。LLM 会严格按照这个 schema 生成参数。

```python
{
    "type": "object",
    "properties": {
        "query": {                              # 参数名
            "type": "string",                   # 类型
            "description": "The search query",  # 参数描述（给 LLM 看）
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return (default 5)",
            "default": 5,                       # 默认值（可选参数的暗示）
        },
    },
    "required": ["query"],  # 必填参数列表
}
```

## 9.8 Step 6：在 main.py 中 import

最后一步，让工具在启动时自动注册：

```python
# main.py

# ── 初始化所有模块 ──
import tool              # 工具框架就绪
import builtin_tools     # 注册内置工具
import search_web_tool   # ← 新增：import 即注册 search_web 工具
import agent
import skill
import task_tool
import session
import llm
```

就这样！`search_web_tool.py` 中的 `tool.define(...)` 调用在 import 时就会执行，工具自动注册到全局注册表。

## 9.9 运行验证

启动 Mini-OpenCode，用 `/tools` 命令查看工具列表：

```
[build] > /tools
  read         Read a file from the filesystem. Returns numbered lines.
  write        Write content to a file. Creates parent directories if needed.
  edit         Replace a unique string in a file. old_string must appear exac
  bash         Execute a shell command and return the output.
  grep         Search file contents using regex pattern.
  glob         Find files matching a glob pattern.
  ask_user     Ask the user a question and wait for their response. Use this
  search_web   Search the web for information using a search engine. Returns
  skill        Load a skill to get detailed instructions for a specific task.
  task         Launch a new agent to handle a task autonomously.
```

然后试试让 Agent 搜索：

```
[build] > 帮我搜索一下 Python asyncio 的最佳实践
```

Agent 会调用 `search_web` 工具，返回搜索结果，然后基于结果给你总结。

## 9.10 进阶：工具开发的常见模式

### 模式 1：需要用户输入的工具（ask_user）

`ask_user` 工具展示了一种特殊模式：工具执行时需要**暂停并等待用户输入**。

```python
async def _ask_user(params: dict, ctx: tool.ToolContext) -> str:
    question = params["question"]

    # 关键：用 run_in_executor 在线程池中调用阻塞的 input()
    loop = asyncio.get_event_loop()
    answer = await loop.run_in_executor(
        None,
        lambda: input("  ▶ 你的回答: "),
    )
    return answer.strip()
```

**为什么不能直接 `input()`？** 因为 `_ask_user` 是 async 函数，在 asyncio 事件循环中执行。`input()` 会阻塞整个事件循环，导致其他异步任务无法执行。`run_in_executor` 把阻塞调用放到线程池中，让事件循环继续运行。

### 模式 2：需要 API Key 的工具

如果你的工具需要 API Key（如 Google Search API），推荐使用环境变量：

```python
import os

async def _search_google(params: dict, ctx: tool.ToolContext) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return "Error: GOOGLE_API_KEY environment variable not set"
    # ... 使用 api_key 调用 API
```

### 模式 3：需要动态描述的工具

有些工具的 description 需要在运行时生成（比如 `task` 工具需要列出可用的 sub-agents）：

```python
def _build_description() -> str:
    """动态构建描述"""
    return "Available agents: " + ", ".join(get_agent_names())

def register_my_tool():
    """显式注册函数，在启动时调用"""
    tool.define(
        name="my_tool",
        description=_build_description(),
        parameters={...},
        execute=_my_execute,
    )
```

这种模式适合 description 依赖运行时状态的工具。参考 `task_tool.py` 和 `skill.py`。

### 模式 4：调用外部服务的工具

`search_web` 就是这个模式。关键点：

1. **超时保护**：外部服务可能很慢，一定要设 `timeout`
2. **错误处理**：网络错误返回友好的错误消息（不是异常栈）
3. **结果截断**：外部服务可能返回大量数据，注意控制返回的文本量
4. **速率限制**：如果调用频繁，考虑加速率限制

## 9.11 练习：自己动手

学完本章，试试自己实现以下工具：

### 练习 1：`fetch_url` 工具

```
功能：获取指定 URL 的网页内容
参数：url (string, required), format ("text" | "html", default "text")
提示：用 requests.get()，注意超时和内容截断
```

### 练习 2：`todo` 工具

```
功能：管理一个简单的待办事项列表
参数：action ("add" | "list" | "done"), item (string, optional)
提示：用一个模块级的 list 存储待办项
```

### 练习 3：`run_python` 工具

```
功能：在沙箱中执行 Python 代码片段
参数：code (string, required)
提示：用 subprocess 调用 python -c，注意安全性
```

每个练习都遵循同样的三步法：

1. 写 async 执行函数
2. 调用 `tool.define()` 注册
3. 在 `main.py` 中 import

## 9.12 总结

自定义工具是扩展 Agent 能力最直接的方式。核心就三件事：

| 步骤 | 做什么 | 为什么 |
|------|--------|--------|
| 1. 执行函数 | `async def _my_tool(params, ctx) -> str` | 实际的工作逻辑 |
| 2. 注册 | `tool.define(name, description, parameters, execute)` | 让框架知道这个工具 |
| 3. Import | 在 `main.py` 中 `import my_tool` | 触发模块级注册代码 |

记住：
- **description 写给 LLM 看**——它决定了 LLM 何时选择这个工具
- **错误返回字符串不抛异常**——让 LLM 有机会自愈
- **控制输出大小**——不要把 10MB 的网页内容全塞给 LLM

**恭喜！** 你已经完成了 Mini-OpenCode 的全部教程。现在你理解了一个现代 AI Coding Agent 的完整架构。去构建你自己的 Agent 吧！
