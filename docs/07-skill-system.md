# 第七章：Skill 插件系统

> 本章目标：理解 `skill.py` 的 Skill 发现、加载和注入机制，掌握知识插件的设计模式。

## 7.1 为什么需要 Skill 系统？

LLM 的知识是通用的。当你需要它遵循特定的编码规范、使用特定的框架、或者执行特定的工作流时，你需要在 prompt 中注入专门的知识。

但如果把所有知识都塞进 system prompt，会有两个问题：
1. **token 浪费**：大部分知识在大部分时间都用不到
2. **注意力稀释**：信息太多，LLM 反而抓不住重点

**Skill 系统** 解决了这个问题：知识按需加载。LLM 在需要时主动调用 `skill` 工具加载相关知识。

## 7.2 Skill 的格式

每个 Skill 是一个目录下的 `SKILL.md` 文件：

```
skills/
└── example/
    └── SKILL.md
```

`SKILL.md` 的格式：

```markdown
---
name: code-review
description: Comprehensive code review checklist for Python projects
---

# Code Review Checklist

## Security
- [ ] No hardcoded secrets
- [ ] Input validation on all user inputs
...

## Performance
- [ ] No N+1 query patterns
...
```

由两部分组成：
1. **YAML frontmatter**（`---` 之间）：定义 name 和 description
2. **Markdown body**：实际的知识内容

## 7.3 Skill 发现

```python
# skill.py:30-44
def discover(directories=None):
    """扫描目录中的 SKILL.md 文件"""
    if directories is None:
        directories = [os.path.join(os.getcwd(), "skills")]

    for base in directories:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if "SKILL.md" in files:
                path = os.path.join(root, "SKILL.md")
                _load(path)
```

`discover()` 递归遍历 `./skills/` 目录，找到所有 `SKILL.md` 文件。这种约定大于配置的设计非常简洁：

- 不需要注册表文件
- 不需要配置文件
- 只需要在正确的位置放置 `SKILL.md`

### 解析 SKILL.md

```python
# skill.py:47-72
def _load(path: str):
    """解析一个 SKILL.md 文件"""
    with open(path, "r") as f:
        raw = f.read()

    # 解析 YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        return

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return

    name = meta.get("name")
    desc = meta.get("description")
    if not name or not desc:
        return

    _skills[name] = SkillInfo(
        name=name,
        description=desc,
        location=path,
        content=match.group(2).strip(),
    )
```

解析过程：
1. 用正则匹配 YAML frontmatter（`---` 包围的部分）
2. 用 `yaml.safe_load` 解析元数据
3. 把 name、description、路径和 markdown 内容存入 `_skills` 字典

`re.DOTALL` 标志让 `.` 匹配换行符，确保多行 YAML 和 markdown 都能正确匹配。

## 7.4 SkillTool：让 LLM 主动加载知识

Skill 发现后，需要注册一个 `skill` 工具，让 LLM 能主动加载：

### 动态描述

```python
# skill.py:86-103
def _build_description():
    """动态构建 SkillTool 的描述，注入可用 skill 列表"""
    skills = all_skills()
    if not skills:
        return "Load a skill. No skills currently available."

    lines = [
        "Load a skill to get detailed instructions for a specific task.",
        "Skills provide specialized knowledge and step-by-step guidance.",
        "<available_skills>",
    ]
    for s in skills.values():
        lines.append(f"  <skill>")
        lines.append(f"    <name>{s.name}</name>")
        lines.append(f"    <description>{s.description}</description>")
        lines.append(f"  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)
```

LLM 看到的工具描述长这样：

```
Load a skill to get detailed instructions for a specific task.
Skills provide specialized knowledge and step-by-step guidance.
<available_skills>
  <skill>
    <name>code-review</name>
    <description>Comprehensive code review checklist for Python projects</description>
  </skill>
</available_skills>
```

注意使用了 XML 标签来结构化 skill 列表。LLM 对 XML 标签的理解非常好，比纯文本列表更精准。

### 执行逻辑

```python
# skill.py:106-113
async def _skill_execute(params, ctx):
    name = params["name"]
    s = get(name)
    if not s:
        return f"Error: Skill '{name}' not found"

    base_dir = os.path.dirname(s.location)
    return f"## Skill: {s.name}\n\n**Base directory**: {base_dir}\n\n{s.content}"
```

执行非常简单：根据 name 查找 skill，返回其 markdown 内容。返回值会被追加到对话历史中，LLM 在后续的推理中就能看到这些知识。

## 7.5 知识注入的完整流程

```
用户: "帮我做一次代码审查"
  │
  ▼
[build agent, Step 1]
LLM 看到 skill 工具的描述，发现有 code-review skill
→ tool_calls: [{name: "skill", args: {name: "code-review"}}]
  │
  ▼
[执行 skill 工具]
→ 返回 code-review 的 markdown 内容
→ 追加到消息历史
  │
  ▼
[build agent, Step 2]
LLM 现在看到了完整的 code review checklist
→ tool_calls: [{name: "read", args: {file_path: "main.py"}}]
  │
  ▼
[后续步骤]
LLM 根据 checklist 逐项检查代码...
```

关键：Skill 内容被注入到消息历史中，而不是 system prompt 中。这意味着：
- 只有在需要时才加载（按需）
- 不会占用每次调用的 system prompt 空间
- LLM 可以在同一个会话中加载多个 skill

## 7.6 创建自己的 Skill

### 步骤

1. 在 `skills/` 目录下创建子目录：
```bash
mkdir -p skills/my-skill
```

2. 创建 `SKILL.md`：
```markdown
---
name: my-skill
description: When to use this skill and what it provides
---

# My Skill Title

## Guidelines

1. First guideline...
2. Second guideline...

## Templates

```python
# Template code...
```

## Checklist

- [ ] Item 1
- [ ] Item 2
```

3. 重启应用，skill 会被自动发现。

### 好的 Skill 设计原则

**1. Description 要精确**

```yaml
# 好的
description: Code review checklist for Python projects covering security, performance, and style

# 不好的
description: 代码审查
```

Description 是 LLM 决定是否加载这个 skill 的唯一依据。

**2. 内容要有操作性**

```markdown
# 好的: 可执行的 checklist
## Security
- [ ] Check all user inputs are validated
- [ ] Ensure no SQL injection via string formatting

# 不好的: 泛泛而谈
## Security
Security is important. Make sure your code is secure.
```

**3. 适度的长度**

Skill 内容会占用 token。太短没有价值，太长浪费资源。一般 200-500 行的 markdown 是合适的。

## 7.7 Skill vs System Prompt

| | System Prompt | Skill |
|---|---|---|
| 何时加载 | 每次 LLM 调用都发送 | 按需加载 |
| 占用位置 | system message | tool result（user/tool turn） |
| 适合场景 | 通用规则、行为约束 | 特定任务的专业知识 |
| Token 消耗 | 每轮都消耗 | 只在使用时消耗一次 |
| 例子 | "Be concise and direct" | "Python code review checklist" |

## 7.8 与 OpenCode 的对照

| 概念 | Mini-OpenCode | OpenCode |
|------|------|------|
| Skill 格式 | YAML frontmatter + Markdown | 相同 |
| 发现机制 | 遍历 `./skills/` | 遍历多个目录（`~/.claude/skills/`、项目目录等） |
| 加载方式 | `skill` 工具 | `skill` 工具 |
| 资源引用 | 无 | Skill 可以引用外部资源文件 |

OpenCode 的 Skill 系统更强大：
- 支持多个搜索目录（全局 skills、项目 skills）
- Skill 可以包含辅助资源文件
- 更丰富的 frontmatter 元数据

## 7.9 设计模式分析

### 约定大于配置

```
skills/
└── <name>/
    └── SKILL.md    ← 只要文件名是 SKILL.md，就自动被发现
```

不需要注册文件、不需要配置列表。放对位置就行。

### 延迟加载

Skill 内容在 `discover()` 时就全部读入内存了。但 LLM 只在需要时才通过 `skill` 工具获取特定 skill 的内容。这是一种应用层面的"延迟注入"。

### 工具化的知识

把知识注入建模为一个"工具"是一个巧妙的设计。它复用了现有的工具框架（注册、权限、调用），不需要任何特殊机制。

## 7.10 思考题

1. **如果 skill 很多（100+），LLM 能看到的 skill 描述列表会很长。如何优化？**
   > 提示：可以分类、分页，或者让 LLM 先搜索 skill。

2. **Skill 内容是在工具执行时返回的，这意味着它只在一次对话中有效。如果需要持久化的知识呢？**
   > 提示：可以把 skill 内容注入到 system prompt 中，但会影响每次调用。

3. **能不能让 Skill 本身包含工具定义？** 比如一个 "database" skill 自带数据库查询工具。
   > 提示：这就是 MCP（Model Context Protocol）的思路——Mini-OpenCode 没有实现但 OpenCode 支持。

**下一章**：[08-system-prompt.md](08-system-prompt.md) —— System Prompt 工程，理解如何组装有效的提示。
