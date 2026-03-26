"""
Mini-OpenCode Web GUI —— 基于 Flask + SSE 的图形界面

设计隐喻：外包团队
  - 每次用户请求 = 用户找到了一个外包团队
  - Agent = 和用户对接的项目经理
  - SubAgent = 外包团队里的员工
  - Tool = 员工使用的工具/技能
  - Session = 一个项目工单

启动方式:
  python web_server.py
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
import io
import threading
import time
import queue
import uuid
from functools import wraps

# 强制 UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from flask import Flask, request, jsonify, Response, send_from_directory

# ── 初始化所有模块 ──
import tool
import builtin_tools
import search_web_tool
import agent as agent_mod
import skill
import task_tool
import session as session_mod
import llm
import system_prompt


app = Flask(__name__, static_folder="static")

# ── 全局状态 ──
_client: llm.Config | None = None
_model: str = ""
_current_session: session_mod.Session | None = None
_current_agent: agent_mod.Agent | None = None

# SSE 事件队列：每个连接一个队列
_event_queues: dict[str, queue.Queue] = {}
_event_lock = threading.Lock()

# 异步事件循环（在单独线程跑）
_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None


def _ensure_loop():
    """确保有一个后台 asyncio 事件循环"""
    global _loop, _loop_thread
    if _loop is not None:
        return
    _loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _loop_thread = threading.Thread(target=run, daemon=True)
    _loop_thread.start()


def broadcast_event(event_type: str, data: dict):
    """向所有 SSE 连接广播事件"""
    event_data = json.dumps(data, ensure_ascii=False)
    with _event_lock:
        for q in _event_queues.values():
            try:
                q.put_nowait(f"event: {event_type}\ndata: {event_data}\n\n")
            except queue.Full:
                pass


# ── 猴子补丁 llm.stream_chat 以捕获流式输出 ──

_original_stream_chat = llm.stream_chat


def _patched_stream_chat(
    client, model, system, messages, tools, temperature=0.7, max_retries=3
):
    """
    包装 llm.stream_chat，拦截流式输出并广播到 SSE。
    """
    # 组装请求体
    full_messages = []
    for s in system:
        if s.strip():
            full_messages.append({"role": "system", "content": s})
    full_messages.extend(messages)

    payload = {
        "model": model,
        "messages": full_messages,
        "stream": True,
        "temperature": temperature,
    }

    import requests as req

    openai_tools = tool.to_openai_tools(tools) if tools else None
    if openai_tools:
        payload["tools"] = openai_tools
        payload["tool_choice"] = "auto"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {client.api_key}",
    }

    resp = None
    for attempt in range(max_retries):
        try:
            resp = req.post(
                client.endpoint,
                headers=headers,
                json=payload,
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()
            break
        except req.exceptions.HTTPError as e:
            status = resp.status_code if resp is not None else None
            if status == 429:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return {
                "role": "assistant",
                "content": f"[LLM Error: HTTP {status}]",
                "tool_calls": None,
                "finish_reason": "error",
            }
        except req.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            return {
                "role": "assistant",
                "content": "[LLM Error: Connection failed]",
                "tool_calls": None,
                "finish_reason": "error",
            }
        except Exception as e:
            return {
                "role": "assistant",
                "content": f"[LLM Error: {e}]",
                "tool_calls": None,
                "finish_reason": "error",
            }

    if resp is None:
        return {
            "role": "assistant",
            "content": "[LLM Error: No response]",
            "tool_calls": None,
            "finish_reason": "error",
        }

    # 流式解析 SSE
    content_parts = []
    tool_calls_map: dict[int, dict] = {}
    finish_reason = None

    resp.encoding = "utf-8"
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if not line.startswith("data: "):
            continue

        data_str = line[6:]
        if data_str.strip() == "[DONE]":
            break

        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        choices = chunk.get("choices", [])
        if not choices:
            continue

        choice = choices[0]
        delta = choice.get("delta", {})

        # 收集文本并广播
        if delta.get("content"):
            text = delta["content"]
            print(text, end="", flush=True)
            content_parts.append(text)
            broadcast_event("token", {"text": text})

        # 收集 tool calls
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

        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]

    if content_parts:
        print()

    content = "".join(content_parts) if content_parts else None

    tool_calls = None
    if tool_calls_map:
        tool_calls = []
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            tool_calls.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
            )

    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
        "finish_reason": finish_reason,
    }


# 替换 llm.stream_chat
llm.stream_chat = _patched_stream_chat


# ── 包装 session.loop 以广播事件 ──

_original_loop = session_mod.loop


async def _patched_loop(session, agent, client, model, on_tool_call=None):
    """包装核心循环，广播步骤和工具调用事件"""
    step = 0
    last_text = ""

    broadcast_event(
        "agent_start",
        {
            "agent": agent.name,
            "session_id": session.id,
            "parent_id": session.parent_id,
            "description": agent.description,
        },
    )

    while step < agent.steps:
        step += 1

        system = system_prompt.build(agent)
        tools = tool.resolve(agent.permissions)

        if step >= agent.steps:
            tools = {}

        broadcast_event(
            "step",
            {
                "step": step,
                "max_steps": agent.steps,
                "agent": agent.name,
                "session_id": session.id,
                "message_count": len(session.messages),
                "tool_count": len(tools),
            },
        )

        response = llm.stream_chat(
            client=client,
            model=model,
            system=system,
            messages=session.messages,
            tools=tools,
        )

        session.add_assistant_message(response)

        if response.get("content"):
            last_text = response["content"]
            broadcast_event(
                "assistant_text",
                {
                    "text": last_text,
                    "agent": agent.name,
                    "session_id": session.id,
                },
            )

        if not response.get("tool_calls"):
            break

        # 执行工具
        for tc in response["tool_calls"]:
            fn = tc["function"]
            name = fn["name"]
            call_id = tc["id"]

            try:
                args = json.loads(fn["arguments"])
            except json.JSONDecodeError:
                args = {}

            broadcast_event(
                "tool_call",
                {
                    "tool": name,
                    "args": {k: str(v)[:200] for k, v in args.items()},
                    "agent": agent.name,
                    "session_id": session.id,
                },
            )

            if on_tool_call:
                on_tool_call(name, args)

            t = tool.get(name)
            if t:
                ctx = tool.ToolContext(session_id=session.id, agent_name=agent.name)
                try:
                    result = await t.execute(args, ctx)
                except Exception as e:
                    result = f"Error executing tool: {e}"
            else:
                result = f"Error: Unknown tool '{name}'"

            preview = result[:300].replace("\n", "\\n")
            broadcast_event(
                "tool_result",
                {
                    "tool": name,
                    "result_preview": preview,
                    "agent": agent.name,
                    "session_id": session.id,
                },
            )

            session.add_tool_result(call_id, name, result)

    broadcast_event(
        "agent_done",
        {
            "agent": agent.name,
            "session_id": session.id,
            "result_preview": last_text[:300] if last_text else "",
        },
    )

    return last_text


session_mod.loop = _patched_loop


# ── 同时需要修补 task_tool 中对 session_mod.loop 的引用 ──
# task_tool 直接调用了 session_mod.loop，已经通过 module 引用所以自动更新


# ── Flask 路由 ──


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


@app.route("/api/status")
def api_status():
    """返回当前系统状态"""
    global _current_agent, _current_session
    agents_list = []
    for a in agent_mod.list_agents():
        agents_list.append(
            {
                "name": a.name,
                "description": a.description,
                "mode": a.mode,
                "steps": a.steps,
                "is_current": a.name == (_current_agent.name if _current_agent else ""),
            }
        )

    tools_list = []
    if _current_agent:
        resolved = tool.resolve(_current_agent.permissions)
        for name, t in resolved.items():
            tools_list.append({"name": name, "description": t.description[:100]})

    skills_list = []
    for name, s in skill.all_skills().items():
        skills_list.append({"name": name, "description": s.description[:80]})

    return jsonify(
        {
            "model": _model,
            "agents": agents_list,
            "tools": tools_list,
            "skills": skills_list,
            "session": {
                "id": _current_session.id if _current_session else None,
                "message_count": len(_current_session.messages)
                if _current_session
                else 0,
            },
        }
    )


@app.route("/api/agents")
def api_agents():
    """返回所有 agent"""
    return jsonify(
        [
            {
                "name": a.name,
                "description": a.description,
                "mode": a.mode,
                "steps": a.steps,
            }
            for a in agent_mod.list_agents()
        ]
    )


@app.route("/api/agent/switch", methods=["POST"])
def api_switch_agent():
    """切换当前 agent"""
    global _current_agent
    data = request.json
    name = data.get("name")
    a = agent_mod.get(name)
    if not a:
        return jsonify({"error": f"Agent '{name}' not found"}), 404
    _current_agent = a
    resolved = tool.resolve(a.permissions)
    return jsonify(
        {
            "agent": a.name,
            "tools": list(resolved.keys()),
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    发送消息并触发 agent loop。
    结果通过 SSE 实时推送。
    """
    global _current_session, _current_agent, _client, _model
    data = request.json
    user_input = data.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "Empty message"}), 400

    # 处理 @agent 语法
    if user_input.startswith("@"):
        parts = user_input.split(maxsplit=1)
        agent_name = parts[0][1:]
        prompt = parts[1] if len(parts) > 1 else ""
        a = agent_mod.get(agent_name)
        if a and a.mode != "primary":
            _current_session.add_user_message(
                f"{prompt}\n\nUse the task tool to delegate this to the '{agent_name}' agent."
            )
        else:
            _current_session.add_user_message(user_input)
    else:
        _current_session.add_user_message(user_input)

    # 广播用户消息
    broadcast_event("user_message", {"text": user_input})

    # 在后台线程运行 agent loop
    def run_loop():
        asyncio.run(
            _patched_loop(
                session=_current_session,
                agent=_current_agent,
                client=_client,
                model=_model,
            )
        )
        broadcast_event("loop_done", {})

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    return jsonify({"status": "started"})


@app.route("/api/session/new", methods=["POST"])
def api_new_session():
    """创建新会话"""
    global _current_session
    _current_session = session_mod.create()
    return jsonify({"session_id": _current_session.id})


@app.route("/api/session/messages")
def api_session_messages():
    """返回当前会话的所有消息"""
    global _current_session
    if not _current_session:
        return jsonify([])

    messages = []
    for msg in _current_session.messages:
        entry = {"role": msg["role"]}
        if msg.get("content"):
            entry["content"] = msg["content"]
        if msg.get("tool_calls"):
            entry["tool_calls"] = [
                {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"][:200],
                }
                for tc in msg["tool_calls"]
            ]
        if msg.get("tool_call_id"):
            entry["tool_call_id"] = msg["tool_call_id"]
            entry["content"] = msg.get("content", "")[:500]
        messages.append(entry)

    return jsonify(messages)


@app.route("/api/events")
def api_events():
    """SSE 端点，推送实时事件"""
    client_id = str(uuid.uuid4())[:8]
    q = queue.Queue(maxsize=1000)

    with _event_lock:
        _event_queues[client_id] = q

    def generate():
        try:
            yield f"event: connected\ndata: {json.dumps({'client_id': client_id})}\n\n"
            while True:
                try:
                    event = q.get(timeout=30)
                    yield event
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with _event_lock:
                _event_queues.pop(client_id, None)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── 修补 ask_user 工具以通过 Web 交互 ──


async def _web_ask_user(params: dict, ctx: tool.ToolContext) -> str:
    """通过 SSE 向前端发送问题，等待用户回答"""
    question_text = params["question"]
    answer_id = str(uuid.uuid4())[:8]

    broadcast_event(
        "ask_user",
        {
            "question": question_text,
            "answer_id": answer_id,
        },
    )

    # 等待用户通过 /api/answer 回答
    _pending_answers[answer_id] = None
    for _ in range(600):  # 最多等 5 分钟
        await asyncio.sleep(0.5)
        if _pending_answers.get(answer_id) is not None:
            answer = _pending_answers.pop(answer_id)
            return answer
    _pending_answers.pop(answer_id, None)
    return "(用户未在限定时间内回答)"


_pending_answers: dict[str, str | None] = {}


@app.route("/api/answer", methods=["POST"])
def api_answer():
    """用户回答 ask_user 的问题"""
    data = request.json
    answer_id = data.get("answer_id")
    answer = data.get("answer", "")
    if answer_id in _pending_answers:
        _pending_answers[answer_id] = answer
        return jsonify({"status": "ok"})
    return jsonify({"error": "Unknown answer_id"}), 404


# ── 启动 ──


def init():
    """初始化系统"""
    global _client, _model, _current_session, _current_agent

    _model = os.environ.get("MODEL", "gpt-4o")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        print("Error: Set OPENAI_API_KEY environment variable")
        sys.exit(1)

    print(f"Model:    {_model}")
    print(f"Base URL: {base_url}")

    # 1. 发现 Skills
    skill.discover()
    skill.register_skill_tool()

    # 2. 创建 LLM 客户端
    _client = llm.create_client()

    # 3. 配置 TaskTool
    task_tool.configure(_client, _model)
    task_tool.register_task_tool()

    # 4. 替换 ask_user 工具为 Web 版
    tool._registry["ask_user"] = tool.ToolDef(
        name="ask_user",
        description=(
            "Ask the user a question and wait for their response. "
            "Use this when you need clarification or confirmation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to ask"},
            },
            "required": ["question"],
        },
        execute=_web_ask_user,
    )

    # 5. 创建初始 Session
    _current_session = session_mod.create()
    _current_agent = agent_mod.get("build")

    print(f"Agent:    {_current_agent.name}")
    print(f"Tools:    {', '.join(tool.resolve(_current_agent.permissions).keys())}")
    print("\n✓ Mini-OpenCode GUI ready at http://localhost:5001")


if __name__ == "__main__":
    init()
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
