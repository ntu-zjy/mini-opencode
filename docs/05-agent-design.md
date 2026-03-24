# 第五章：Agent 设计与权限系统

> 本章目标：理解 `agent.py` 中的多角色 Agent 设计，掌握权限系统如何约束 Agent 行为。

## 5.1 为什么需要多个 Agent？

一个全能的 Agent 不就够了吗？理论上可以，但多 Agent 设计有几个关键优势：

1. **最小权限原则**：不是所有任务都需要写文件和执行命令。只读的 Agent 更安全。
2. **专注性**：给 LLM 一个明确的角色，它的输出质量更高。
3. **效率**：搜索代码的 Agent 不需要加载写文件的工具，减少 token 消耗。
4. **可组合性**：不同 Agent 可以协作（通过 Sub-Agent 委派）。

## 5.2 Agent 定义

```python
# agent.py:16-23
@dataclass
class Agent:
    name: str                # 唯一标识符
    description: str = ""    # 描述（给 LLM 和用户看）
    mode: str = "all"        # "primary" | "subagent" | "all"
    prompt: str = ""         # 自定义 system prompt
    model: str = ""          # 绑定模型（空 = 用默认）
    permissions: dict = field(default_factory=lambda: {"*": "allow"})
    steps: int = 50          # 最大迭代次数
```

七个字段，每个都很重要：

### `mode` - 使用模式

```
primary   → 只能被用户直接使用（通过 /agent 命令切换）
subagent  → 只能被其他 Agent 通过 task 工具调用
all       → 两者都可以
```

这个设计很精妙：`explore` agent 被设定为 `subagent` 模式，意味着用户不能直接切换到它，但 `build` agent 可以通过 `task` 工具委派任务给它。这创造了一种层次化的 Agent 架构。

### `prompt` - 角色定义

```python
# build agent
prompt = "You are an expert software engineer. You help users write, debug, and improve code."

# plan agent
prompt = "You are a planning assistant. Analyze requirements and create plans. NEVER modify files."

# explore agent
prompt = "You are a codebase exploration specialist. Find files, read code, answer questions."
```

注意 `plan` agent 的 prompt 中有 "NEVER modify files" 的强调。这是**双重保险**——除了权限过滤，prompt 也明确禁止修改。LLM 遵循 prompt 指令 + 没有修改工具可用 = 双层保护。

### `permissions` - 权限映射

权限是一个字典，key 是工具名（或 `*` 通配符），value 是 `"allow"` 或 `"deny"`：

```python
# build: 全能
{"*": "allow"}

# plan: 允许读取和搜索，禁止修改
{"*": "allow", "write": "deny", "edit": "deny", "bash": "deny"}

# explore: 默认禁止，只允许搜索和读取
{"*": "deny", "read": "allow", "grep": "allow", "glob": "allow", "bash": "allow"}
```

### `steps` - 迭代上限

不同 Agent 的步数上限不同，反映了它们任务的复杂度：

```
build:   50 步  ← 复杂的编码任务可能需要很多轮
plan:    20 步  ← 规划任务通常不需要太多轮
explore: 30 步  ← 搜索任务介于两者之间
```

## 5.3 三个内置 Agent 的设计思路

### build - 全能工程师

```python
Agent(
    name="build",
    description="General purpose coding agent. Can read, write, and execute code.",
    mode="primary",
    prompt="You are an expert software engineer...",
    permissions={"*": "allow"},
    steps=50,
)
```

这是默认 Agent，拥有所有权限。它是用户的主要交互对象，能做任何事情：
- 读写文件
- 执行命令
- 搜索代码
- 委派任务给子 Agent
- 加载 Skill

### plan - 只读规划师

```python
Agent(
    name="plan",
    description="Read-only planning agent. Cannot modify files.",
    mode="primary",
    prompt="You are a planning assistant. Analyze requirements and create plans. NEVER modify files.",
    permissions={"*": "allow", "write": "deny", "edit": "deny", "bash": "deny"},
    steps=20,
)
```

为什么需要一个不能写代码的 Agent？

1. **安全浏览**：当你只想让 AI 分析代码而不修改时
2. **架构设计**：制定计划时不需要执行能力
3. **代码审查**：只读取和分析，不改动

注意：`plan` 的权限允许 `read`、`grep`、`glob`（因为这些没有被显式 deny），但禁止 `write`、`edit`、`bash`。它还能使用 `task` 和 `skill` 工具（委派给子 Agent 和加载知识）。

### explore - 搜索专家

```python
Agent(
    name="explore",
    description="Fast codebase exploration agent. Good at searching and reading code.",
    mode="subagent",
    prompt="You are a codebase exploration specialist...",
    permissions={"*": "deny", "read": "allow", "grep": "allow", "glob": "allow", "bash": "allow"},
    steps=30,
)
```

关键点：
- `mode="subagent"` → 不能被用户直接使用，只能被其他 Agent 委派
- `"*": "deny"` → 默认禁止所有工具
- 只允许 `read`、`grep`、`glob`、`bash` → 纯搜索能力
- 没有 `task` 权限 → 不能再委派给其他 Agent（避免递归委派）

## 5.4 权限过滤的完整流程

让我们追踪 `plan` agent 的工具过滤过程：

```python
# 全局注册表中的所有工具:
_registry = {
    "read": ..., "write": ..., "edit": ...,
    "bash": ..., "grep": ..., "glob": ...,
    "task": ..., "skill": ...
}

# plan agent 的权限:
permissions = {"*": "allow", "write": "deny", "edit": "deny", "bash": "deny"}

# tool.resolve() 的执行过程:
default = "allow"   # permissions["*"]

# 遍历每个工具:
# read:  permissions.get("read", "allow")  = "allow"  → 包含
# write: permissions.get("write", "allow") = "deny"   → 排除
# edit:  permissions.get("edit", "allow")  = "deny"   → 排除
# bash:  permissions.get("bash", "allow")  = "deny"   → 排除
# grep:  permissions.get("grep", "allow")  = "allow"  → 包含
# glob:  permissions.get("glob", "allow")  = "allow"  → 包含
# task:  permissions.get("task", "allow")  = "allow"  → 包含
# skill: permissions.get("skill", "allow") = "allow"  → 包含

# 结果: {read, grep, glob, task, skill}
```

## 5.5 Agent 注册与发现

```python
# agent.py:28-33
AGENTS: dict[str, Agent] = {}

def _register(a: Agent):
    AGENTS[a.name] = a
    return a
```

和工具一样，Agent 也使用全局注册表。三个内置 Agent 在模块级注册：

```python
_register(Agent(name="build", ...))
_register(Agent(name="plan", ...))
_register(Agent(name="explore", ...))
```

### Sub-Agent 发现

```python
# agent.py:94-107
def subagents(caller=None):
    """获取可用子 agent 列表"""
    result = []
    for a in AGENTS.values():
        if a.mode == "primary":
            continue        # 排除 primary 模式的 Agent
        if a.description:   # 没有 description 的不暴露给 LLM
            result.append(a)
    return result
```

这个函数被 `task_tool.py` 用来构建 TaskTool 的描述。它过滤掉 `mode="primary"` 的 Agent，因为主 Agent 不应该被自己或其他 Agent 委派。

## 5.6 自定义 Agent

注册自定义 Agent 非常简单：

```python
import agent

# 代码审查专家
agent.register(agent.Agent(
    name="reviewer",
    description="Code review specialist. Finds bugs and suggests improvements.",
    mode="subagent",
    prompt="You are a meticulous code reviewer. Focus on: bugs, security issues, performance, readability.",
    permissions={"*": "allow", "write": "deny", "edit": "deny"},
    steps=25,
))

# 文档写手
agent.register(agent.Agent(
    name="doc-writer",
    description="Documentation writer. Creates clear, comprehensive docs.",
    mode="all",
    prompt="You are a technical writer. Create clear documentation with examples.",
    permissions={"*": "allow"},
    steps=30,
))
```

注册后，`build` agent 就可以通过 `task` 工具委派任务给 `reviewer` 或 `doc-writer`。

## 5.7 Agent 与 Prompt 的关系

每个 Agent 的 `prompt` 会和 `BASE_PROMPT` 合并（详见[第八章](08-system-prompt.md)）：

```python
# system_prompt.py:48-52
if ag.prompt:
    parts.append(ag.prompt + "\n\n" + BASE_PROMPT)
else:
    parts.append(BASE_PROMPT)
```

最终发送给 LLM 的 system prompt 结构是：

```
[Agent 专属 prompt]
You are an expert software engineer...

[通用 BASE_PROMPT]
## Tone and style
- Be concise and direct...
## Tool usage
- Use tools to complete tasks...

[环境信息]
<env>
  Working directory: /path/to/project
  ...
</env>

[自定义规则（如果有 AGENTS.md）]
```

## 5.8 设计模式分析

### 最小权限原则

```
build:   *:allow                     → 全部能力
plan:    *:allow, write/edit/bash:deny → 只读
explore: *:deny, read/grep/glob:allow  → 只搜索
```

从上到下，权限逐步收紧。每个 Agent 只拥有完成其任务所需的最少权限。

### 角色 + 权限的双层约束

Agent 的行为受两层约束：
1. **Prompt 约束**：通过自然语言指令引导 LLM 的行为倾向
2. **权限约束**：通过工具过滤硬性限制 LLM 的行动能力

即使 LLM 违反了 prompt 指令想要写文件，如果工具列表中没有 `write`，它也无法做到。

### 可扩展的 Agent 注册

新 Agent 的添加不需要修改任何现有代码：

```python
# 在任何地方调用即可
agent.register(Agent(name="my-agent", ...))
```

## 5.9 思考题

1. **如果你要设计一个"测试运行器" Agent，它的 permissions 应该怎么设置？**
   > 提示：需要 bash（运行测试）、read（读取测试文件）、grep（搜索失败原因）。不需要 write/edit（不修改代码）。

2. **`explore` agent 允许 `bash` 但不允许 `write`/`edit`。为什么？`bash` 能不能做 `write` 做的事？**
   > 提示：`bash` 确实可以通过 `echo > file` 写文件。权限系统不是防恶意用户的，而是引导 LLM 行为的。

3. **如果两个 Agent 可以互相委派任务，会发生什么？如何防止无限递归？**
   > 提示：当前 `explore` 不能使用 `task` 工具。但如果移除这个限制呢？

**下一章**：[06-sub-agent.md](06-sub-agent.md) —— Sub-Agent 委派机制，理解 Agent 之间的协作。
