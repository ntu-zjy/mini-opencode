# 第八章：System Prompt 工程

> 本章目标：理解 `system_prompt.py` 的 Prompt 组装逻辑，掌握面向 Agent 的 Prompt 设计。

## 8.1 System Prompt 在 Agent 中的角色

System Prompt 是 Agent 的 "操作系统"——它定义了 Agent 的身份、行为规范和工作方式。每次调用 LLM 时，system prompt 都作为第一条消息发送。

在 Agent 架构中，system prompt 需要承担比普通聊天机器人更多的职责：

```
普通聊天机器人的 system prompt:
  "You are a helpful assistant."

Coding Agent 的 system prompt:
  Agent 身份 + 通用规范 + 工具使用指南 + 环境信息 + 自定义规则
```

## 8.2 Prompt 组装的三层结构

```python
# system_prompt.py:40-63
def build(ag: agent_mod.Agent) -> list[str]:
    """组装完整的 system prompt"""
    parts = []

    # Layer 1: Agent prompt + Base prompt
    if ag.prompt:
        parts.append(ag.prompt + "\n\n" + BASE_PROMPT)
    else:
        parts.append(BASE_PROMPT)

    # Layer 2: 环境信息
    env = _environment()
    parts[0] += "\n\n" + env

    # Layer 3: 自定义规则
    rules = _custom_rules()
    if rules:
        parts[0] += "\n\n" + rules

    return parts
```

返回的是 `list[str]`，每个元素对应一个 system message。当前实现只用了一个元素，但这个设计为多段 system message 留了空间。

### Layer 1: Agent Prompt + Base Prompt

```python
# 以 build agent 为例
ag.prompt = "You are an expert software engineer. You help users write, debug, and improve code."

# 合并后:
"You are an expert software engineer. You help users write, debug, and improve code.

You are an AI coding assistant. You help users with software engineering tasks.

## Tone and style
- Be concise and direct. Output is displayed in a terminal.
- Use markdown formatting.
- Only use emojis if the user explicitly requests it.

## Tool usage
- Use tools to complete tasks. Prefer specialized tools over bash when possible.
- Use read to read files, edit to modify files, write to create files.
- Use grep to search file contents, glob to find files by pattern.
- Use bash for shell commands that need execution.

## Task execution
- Think step by step before acting.
- Read relevant files before making changes.
- Verify changes work after making them."
```

Agent 专属 prompt 在前，通用指南在后。这个顺序很重要：LLM 对 prompt 开头的内容给予更多注意力。

### Layer 2: 环境信息

```python
# system_prompt.py:66-78
def _environment():
    cwd = os.getcwd()
    is_git = os.path.isdir(os.path.join(cwd, ".git"))
    today = datetime.now().strftime("%a %b %d %Y")

    return f"""\
<env>
  Working directory: {cwd}
  Is directory a git repo: {"yes" if is_git else "no"}
  Platform: {platform.system().lower()}
  Today's date: {today}
</env>"""
```

环境信息用 XML 标签 `<env>` 包裹。为什么？

1. **结构化**：LLM 能清晰区分环境信息和其他指令
2. **可提取**：LLM 可以精确引用环境变量
3. **惯例**：OpenAI 和 Anthropic 都推荐用 XML 标签组织 system prompt

LLM 使用这些信息来：
- 构造正确的文件路径（Working directory）
- 判断是否可用 git 命令（Is git repo）
- 使用正确的命令格式（Platform: darwin vs linux）
- 知道当前日期（避免时间相关的错误）

### Layer 3: 自定义规则

```python
# system_prompt.py:81-97
def _custom_rules():
    """加载自定义规则文件 AGENTS.md"""
    cwd = os.getcwd()
    candidates = [
        os.path.join(cwd, "AGENTS.md"),
        os.path.join(cwd, ".opencode", "AGENTS.md"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r") as f:
                content = f.read()
            return f"Instructions from: {path}\n{content}"

    return ""
```

`AGENTS.md` 是项目级的自定义规则。你可以在项目根目录放一个 `AGENTS.md` 来定制 Agent 的行为：

```markdown
# Project Rules

- This is a Python 3.12 project using FastAPI
- Always use type hints
- Follow PEP 8 style guide
- Tests should go in the `tests/` directory
- Use pytest for testing
```

## 8.3 BASE_PROMPT 设计分析

```python
BASE_PROMPT = """\
You are an AI coding assistant. You help users with software engineering tasks.

## Tone and style
- Be concise and direct. Output is displayed in a terminal.
- Use markdown formatting.
- Only use emojis if the user explicitly requests it.

## Tool usage
- Use tools to complete tasks. Prefer specialized tools over bash when possible.
- Use read to read files, edit to modify files, write to create files.
- Use grep to search file contents, glob to find files by pattern.
- Use bash for shell commands that need execution.

## Task execution
- Think step by step before acting.
- Read relevant files before making changes.
- Verify changes work after making them.
"""
```

这个 prompt 虽然只有约 20 行，但每一行都有用：

### 输出格式指导

```
Be concise and direct. Output is displayed in a terminal.
```

告诉 LLM 它的输出环境是终端，所以不要生成太长或太花哨的内容。

### 工具偏好

```
Prefer specialized tools over bash when possible.
```

为什么？因为 LLM 有时会把所有事情都用 `bash` 做（`cat file`, `echo > file`, `find .`）。但专用工具（`read`, `write`, `glob`）更安全、输出更结构化、且可以被权限系统精确控制。

### 工作方法

```
Think step by step before acting.
Read relevant files before making changes.
Verify changes work after making them.
```

这三条规则引导 LLM 遵循"先理解、再修改、后验证"的工作流，而不是盲目修改代码。

## 8.4 Prompt 工程的最佳实践

从 Mini-OpenCode 的设计中，可以提炼出以下 Agent Prompt 设计原则：

### 1. 分层组织

```
Agent 身份 → 通用规范 → 环境信息 → 项目规则
```

从最重要到最具体，逐层叠加。

### 2. 使用结构化标记

```xml
<env>
  Working directory: /path/to/project
</env>
```

XML 标签比纯文本更易于 LLM 理解和引用。

### 3. 正面指令优于负面指令

```
# 好的
"Use read to read files"

# 不好的
"Don't use cat to read files"
```

告诉 LLM 该做什么，而不是不该做什么。正面指令更容易被遵循。

### 4. 工具使用指南

明确告诉 LLM 每个工具的适用场景：

```
Use read to read files, edit to modify files, write to create files.
Use grep to search file contents, glob to find files by pattern.
```

这比让 LLM 自己从工具描述中推断更可靠。

### 5. 动态信息分离

环境信息是动态的（cwd、date），应该和静态指令分开。Mini-OpenCode 用 `<env>` 标签来实现这个分离。

## 8.5 不同 Agent 的 Prompt 差异

```
[build agent]
"You are an expert software engineer. You help users write, debug, and improve code."
+ BASE_PROMPT
→ 全能，强调实践

[plan agent]
"You are a planning assistant. Analyze requirements and create plans. NEVER modify files."
+ BASE_PROMPT
→ 只读，强调分析

[explore agent]
"You are a codebase exploration specialist. Find files, read code, answer questions."
+ BASE_PROMPT
→ 搜索，强调发现
```

每个 Agent 的 prompt 前缀设定了不同的"人格"，引导 LLM 用不同的风格工作。

## 8.6 与 OpenCode 的对照

| 概念 | Mini-OpenCode | OpenCode |
|------|------|------|
| 组装函数 | `system_prompt.build()` | `SystemPrompt.build()` |
| Agent prompt | 简单字符串 | 详细的多段 prompt |
| 环境信息 | cwd, git, platform, date | + workspace root, shell |
| 自定义规则 | `AGENTS.md` | `AGENTS.md` + `.opencode/AGENTS.md` |
| Base prompt | ~20 行 | ~200+ 行（更详细的工具指南） |

OpenCode 的 system prompt 更长、更详细，包含了：
- 更精确的工具使用指南（每个工具的 do/don't）
- Git 操作规范
- Commit message 格式
- PR 创建流程
- 安全规则

## 8.7 思考题

1. **如果你要把 BASE_PROMPT 翻译成中文，LLM 的行为会有什么变化？**
   > 提示：中文 prompt 可能让 LLM 更倾向于用中文回复，但对工具调用的影响有限。

2. **环境信息中还可以包含哪些有用的信息？**
   > 提示：项目语言、框架版本、当前 git branch、最近的 commit...

3. **AGENTS.md 和 Skill 都可以注入知识给 LLM。它们的使用场景有什么区别？**
   > 提示：AGENTS.md 是项目级的常驻规则，Skill 是按需加载的任务知识。

**下一章**：[09-hands-on.md](09-hands-on.md) —— 动手练习，通过实践巩固所学。
