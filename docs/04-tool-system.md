# 第四章：工具框架与内置工具

> 本章目标：理解 `tool.py` 和 `builtin_tools.py`，掌握 Function Calling 的实现原理。

## 4.1 Function Calling：让 LLM 使用工具

LLM 天生只能输出文本。**Function Calling** 是一种让 LLM "调用函数" 的协议：

1. 你告诉 LLM："这些工具可用"（附带参数格式）
2. LLM 想使用某个工具时，输出一个结构化的工具调用（而不是纯文本）
3. 你的代码执行这个工具，把结果反馈给 LLM
4. LLM 基于结果继续推理

LLM 本身不执行任何代码。它只是说"我想调用 `write` 函数，参数是..."，执行由你的代码完成。

## 4.2 工具定义框架 (`tool.py`)

### ToolDef：工具的定义

```python
# tool.py:26-32
@dataclass
class ToolDef:
    """一个工具的完整定义"""
    name: str                      # 工具 ID，如 "read"
    description: str               # 描述（给 LLM 看的）
    parameters: dict               # JSON Schema 格式的参数定义
    execute: Callable[[dict, ToolContext], Awaitable[str]]  # 执行函数
```

四个字段，各有用处：
- `name`：LLM 通过这个名字来调用工具
- `description`：LLM 通过这段描述来理解工具的用途（Prompt 工程的一部分！）
- `parameters`：JSON Schema 格式，告诉 LLM 参数有哪些、什么类型
- `execute`：实际执行逻辑，接收参数和上下文，返回字符串结果

### ToolContext：执行时的上下文

```python
# tool.py:17-22
@dataclass
class ToolContext:
    """传给每个 tool.execute 的运行时上下文"""
    session_id: str
    agent_name: str
```

上下文告诉工具"谁在调用我"。虽然当前简化了，但在 OpenCode 中还包含权限检查、abort 控制等。

### 全局注册表

```python
# tool.py:37-59
_registry: dict[str, ToolDef] = {}

def define(name, description, parameters, execute):
    """注册一个工具"""
    t = ToolDef(name=name, description=description, parameters=parameters, execute=execute)
    _registry[name] = t
    return t
```

这是一个经典的**全局注册表模式**。任何模块只要调用 `tool.define()`，工具就自动注册。好处：

- 主程序不需要知道有哪些工具
- 新增工具只需在新模块中调用 `define()`，无需修改其他代码
- 运行时可以动态注册工具（如 `task` 和 `skill` 工具就是动态注册的）

### 权限过滤

```python
# tool.py:70-83
def resolve(permissions: dict[str, str]) -> dict[str, ToolDef]:
    """按权限过滤工具"""
    result = {}
    default = permissions.get("*", "allow")     # 默认策略
    for name, tool in _registry.items():
        action = permissions.get(name, default)  # 具体工具的策略
        if action != "deny":
            result[name] = tool
    return result
```

权限过滤的逻辑很优雅：

```python
# build agent: 全部允许
{"*": "allow"}
# 结果: 所有工具

# plan agent: 允许读取，禁止修改
{"*": "allow", "write": "deny", "edit": "deny", "bash": "deny"}
# 结果: read, grep, glob, task, skill

# explore agent: 默认禁止，只允许特定工具
{"*": "deny", "read": "allow", "grep": "allow", "glob": "allow", "bash": "allow"}
# 结果: read, grep, glob, bash
```

`*` 是通配符，设定默认策略。具体工具名的设置覆盖默认值。

### 转换为 OpenAI 格式

```python
# tool.py:86-98
def to_openai_tools(tools: dict[str, ToolDef]) -> list[dict]:
    """将工具列表转为 OpenAI function calling 格式"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools.values()
    ]
```

这个函数把内部的 `ToolDef` 转换成 OpenAI API 要求的格式。LLM 看到的是：

```json
{
  "type": "function",
  "function": {
    "name": "read",
    "description": "Read a file from the filesystem. Returns numbered lines.",
    "parameters": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string", "description": "Absolute path to the file"},
        "offset": {"type": "integer", "description": "Line offset (0-based)", "default": 0},
        "limit": {"type": "integer", "description": "Max lines to read", "default": 2000}
      },
      "required": ["file_path"]
    }
  }
}
```

## 4.3 内置工具 (`builtin_tools.py`)

Mini-OpenCode 实现了 7 个内置工具，覆盖了 Coding Agent 的核心操作：

```
文件操作: read → write → edit
命令执行: bash
代码搜索: grep → glob
用户交互: ask_user
```

此外还有 1 个自定义工具示例：

```
外部信息: search_web (search_web_tool.py)
```

### 通用辅助：截断函数

```python
# builtin_tools.py:16-24
MAX_OUTPUT = 8000

def _truncate(text: str, max_len: int = MAX_OUTPUT) -> str:
    if len(text) <= max_len:
        return text
    half = max_len // 2
    removed = len(text) - max_len
    return text[:half] + f"\n\n... ({removed} chars truncated) ...\n\n" + text[-half:]
```

为什么需要截断？因为工具输出会被发回给 LLM 作为上下文。如果一个文件有 10 万行，把全部内容放进上下文会：
1. 超出 token 限制
2. 浪费 API 费用
3. 降低 LLM 的注意力质量

截断策略保留了**前半部分和后半部分**，因为开头和结尾通常比中间更有信息价值。

### read 工具

```python
# builtin_tools.py:30-75
async def _read(params: dict, ctx: tool.ToolContext) -> str:
    path = params["file_path"]
    offset = params.get("offset", 0)
    limit = params.get("limit", 2000)

    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    if os.path.isdir(path):
        entries = os.listdir(path)
        return f"Directory listing of {path}:\n" + "\n".join(entries)

    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    selected = lines[offset : offset + limit]
    numbered = [f"{i + offset + 1:6}\t{line}" for i, line in enumerate(selected)]
    result = "".join(numbered)

    if len(lines) > offset + limit:
        result += f"\n... ({len(lines) - offset - limit} more lines)"

    return _truncate(result)
```

设计要点：
- **带行号输出**：`f"{i + offset + 1:6}\t{line}"` — LLM 需要行号来定位代码
- **分页支持**：`offset` + `limit` 让 LLM 可以分段读取大文件
- **目录支持**：传入目录路径时，列出目录内容
- **错误容忍**：`errors="replace"` 处理非 UTF-8 文件

### write 工具

```python
# builtin_tools.py:81-104
async def _write(params: dict, ctx: tool.ToolContext) -> str:
    path = params["file_path"]
    content = params["content"]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

    lines = content.count("\n") + 1
    return f"Wrote {lines} lines to {path}"
```

简洁而实用。`os.makedirs(..., exist_ok=True)` 自动创建不存在的父目录。

### edit 工具（重点）

```python
# builtin_tools.py:111-148
async def _edit(params: dict, ctx: tool.ToolContext) -> str:
    path = params["file_path"]
    old = params["old_string"]
    new = params["new_string"]

    with open(path, "r") as f:
        content = f.read()

    count = content.count(old)
    if count == 0:
        return "Error: old_string not found in file"
    if count > 1:
        return f"Error: old_string found {count} times. Provide more context to make it unique."

    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)

    return f"Edited {path}: replaced 1 occurrence"
```

**为什么要求 `old_string` 唯一？**

这是一个关键的安全设计。如果允许替换多个匹配项，LLM 可能会意外修改不该修改的地方。要求唯一性迫使 LLM 提供足够的上下文来精确定位要修改的代码。

当 LLM 遇到 "found N times" 错误时，它会在下一轮提供更多周围代码行来唯一定位。这就是 Agent Loop 自我修正的一个典型案例。

### bash 工具

```python
# builtin_tools.py:154-201
async def _bash(params: dict, ctx: tool.ToolContext) -> str:
    command = params["command"]
    timeout = params.get("timeout", 30)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
        if not output:
            output = "(no output)"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return _truncate(output)
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
```

设计要点：
- **stdout + stderr 分离显示**：LLM 需要区分正常输出和错误输出
- **超时保护**：默认 30 秒，防止无限运行的命令
- **退出码**：非零退出码附加在输出末尾，帮助 LLM 判断命令是否成功
- **`shell=True`**：允许使用管道、通配符等 shell 特性

> **安全警告**：`shell=True` + 无权限检查意味着 LLM 可以执行任何命令。OpenCode 通过 Permission Ask 模式在执行前询问用户确认。

### grep 和 glob 工具

```python
# grep: 内容搜索
async def _grep(params, ctx):
    cmd = f'grep -rn "{pattern}" "{path}"'
    if include:
        cmd += f' --include="{include}"'
    cmd += " 2>/dev/null | head -50"    # 限制 50 条结果
    ...

# glob: 文件名匹配
async def _glob(params, ctx):
    full_pattern = os.path.join(path, pattern)
    matches = sorted(glob_mod.glob(full_pattern, recursive=True))
    lines = matches[:100]   # 限制 100 个结果
    ...
```

两者的区别：
- `grep`：搜索文件**内容**（"哪些文件包含 TODO？"）
- `glob`：搜索文件**名称**（"有哪些 .py 文件？"）

两者都有结果数量限制（50/100），避免输出爆炸。

### ask_user 工具（用户交互）

```python
# builtin_tools.py
async def _ask_user(params: dict, ctx: tool.ToolContext) -> str:
    question = params["question"]

    print()
    print("  ┌─ 🤖 Agent 有问题想问你 ─────────────────────")
    print(f"  │  {question}")
    print("  └─────────────────────────────────────────────")

    loop = asyncio.get_event_loop()
    answer = await loop.run_in_executor(
        None,
        lambda: input("  ▶ 你的回答: "),
    )
    return answer.strip() if answer else "(用户未回答)"
```

这个工具比较特殊：它不操作文件或执行命令，而是**暂停 Agent Loop，等待用户输入**。

设计要点：
- **`asyncio.run_in_executor`**：`input()` 是阻塞调用，不能在 async 函数中直接使用。用 `run_in_executor` 将它放到线程池中执行，避免阻塞事件循环。
- **可视化提示**：用边框和图标让用户在终端中注意到 Agent 在等待回答。
- **使用场景**：确认危险操作、在多个方案中选择、补充缺失的需求信息。

### search_web 工具（自定义工具示例）

`search_web` 定义在单独的 `search_web_tool.py` 中，演示了如何编写**自定义工具**：

```python
# search_web_tool.py
async def _search_web(params: dict, ctx: tool.ToolContext) -> str:
    query = params["query"]
    max_results = params.get("max_results", 5)

    results = _search_duckduckgo(query, max_results)
    return _format_results(results, query)
```

设计要点：
- **独立模块**：自定义工具可以放在单独的文件中，只需在 `main.py` 中 `import` 即可。
- **无需 API Key**：使用 DuckDuckGo HTML 搜索，零配置即可使用。
- **结果格式化**：将搜索结果转换为 LLM 友好的 Markdown 格式。
- **错误处理**：超时、网络错误等都有优雅的降级处理。

> 详细的自定义工具教程见 [09-hands-on.md](09-hands-on.md)。

## 4.4 工具注册的时机

理解工具注册的时序很重要：

```python
# main.py 的 import 顺序
import tool              # 工具框架就绪
import builtin_tools     # ← import 时即注册 7 个内置工具
import search_web_tool   # ← import 时即注册 search_web 自定义工具

# 后续动态注册
skill.discover()
skill.register_skill_tool()     # 注册 skill 工具
task_tool.configure(client, model)
task_tool.register_task_tool()  # 注册 task 工具
```

`builtin_tools.py` 和 `search_web_tool.py` 中的 `tool.define(...)` 调用在模块被 import 时就执行了（模块级代码）。而 `task` 和 `skill` 工具需要依赖运行时信息（LLM 配置、已发现的 skills），所以需要显式调用注册函数。

## 4.5 工具 Description 的重要性

工具的 `description` 不是给人看的——它是给 LLM 看的 prompt 的一部分：

```python
# 好的 description
"Read a file from the filesystem. Returns numbered lines."

# 不好的 description
"读取文件"
```

好的 description 应该：
1. 说明工具做什么
2. 说明输入输出格式
3. 暗示使用场景

LLM 根据 description 决定在什么情况下调用哪个工具。description 写得好，LLM 的工具选择就更准确。

## 4.6 JSON Schema 参数定义

每个工具的 `parameters` 使用 JSON Schema 格式：

```python
{
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Absolute path to the file"
        },
        "offset": {
            "type": "integer",
            "description": "Line offset (0-based)",
            "default": 0
        },
    },
    "required": ["file_path"]
}
```

LLM 会严格按照这个 schema 生成参数。`required` 字段告诉 LLM 哪些参数必须提供，`default` 暗示可选参数的默认值。

## 4.7 思考题

1. **`search_web` 工具已经实现了，试着理解它的结构。** 能否将其改为调用 Google 或 Bing 的 API？
   > 提示：参考 `search_web_tool.py` 的实现，替换 `_search_duckduckgo()` 函数即可。

2. **`edit` 工具的"唯一性"约束可以放松吗？** 比如加一个 `replace_all` 参数？
   > 提示：考虑 LLM 误操作的风险和 Coding Agent 中 edit 的使用场景。

3. **`bash` 工具的安全风险有哪些？** 如何在不影响功能的前提下增加安全性？
   > 提示：参考 OpenCode 的 Permission Ask 模式。现在有了 `ask_user` 工具，能否让 Agent 在执行危险命令前先用 `ask_user` 询问用户？

4. **`ask_user` 工具使用了 `asyncio.run_in_executor`，为什么不能直接调用 `input()`？**
   > 提示：`_ask_user` 是一个 async 函数，`input()` 会阻塞整个事件循环。

**下一章**：[05-agent-design.md](05-agent-design.md) —— 理解不同 Agent 角色的设计和权限系统。
