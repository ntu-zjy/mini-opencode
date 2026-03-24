"""
LLM 调用层 —— 对应 OpenCode 的 src/session/llm.ts

直接用 requests 调用 OpenAI 兼容 API（不依赖 openai SDK）。
支持任何兼容接口：OpenAI, DeepSeek, Ollama, vLLM, 美团 AIGC 等。

流式处理：手动解析 SSE (text/event-stream) 响应，
逐 chunk 拼接 content 和 tool_calls。
"""

from __future__ import annotations
import os
import sys
import io
import json
import logging
import time

import requests

import tool

log = logging.getLogger(__name__)

# 确保 stdout 是 UTF-8，防止中文流式输出乱码
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── 配置 ──────────────────────────────────────────────


class Config:
    """LLM 连接配置，从环境变量读取"""

    api_key: str = ""
    base_url: str = ""
    model: str = ""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.environ.get("MODEL", "gpt-4o")
        # 确保 base_url 以 /chat/completions 结尾时直接用，否则拼接
        if self.base_url.endswith("/chat/completions"):
            self.endpoint = self.base_url
        else:
            self.endpoint = self.base_url.rstrip("/") + "/chat/completions"


_config: Config | None = None


def create_client() -> Config:
    """创建配置实例（替代原来的 OpenAI client）"""
    global _config
    _config = Config()
    return _config


# ── 核心调用 ──────────────────────────────────────────


def stream_chat(
    client: Config,
    model: str,
    system: list[str],
    messages: list[dict],
    tools: dict[str, tool.ToolDef],
    temperature: float = 0.7,
    max_retries: int = 3,
) -> dict:
    """
    调用 LLM 并流式输出。对应 OpenCode 的 LLM.stream()。

    使用 requests + SSE 手动解析，不依赖 openai SDK。
    返回完整的 assistant message dict（可能包含 tool_calls）。

    参数:
      client:      Config 配置
      model:       模型名称
      system:      system prompt 数组（每个元素是一段）
      messages:    对话历史（OpenAI 格式）
      tools:       可用工具
      temperature: 采样温度
      max_retries: 最大重试次数
    """
    # ── 1. 组装请求体 ──
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

    openai_tools = tool.to_openai_tools(tools) if tools else None
    if openai_tools:
        payload["tools"] = openai_tools
        payload["tool_choice"] = "auto"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {client.api_key}",
    }

    # ── 2. 带重试的请求 ──
    resp = None
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
            if status == 429:
                wait = 2 ** (attempt + 1)
                log.warning(
                    f"Rate limited (429), waiting {wait}s (attempt {attempt + 1})"
                )
                time.sleep(wait)
                continue
            log.error(f"HTTP error {status}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return {
                "role": "assistant",
                "content": f"[LLM Error: HTTP {status}]",
                "tool_calls": None,
                "finish_reason": "error",
            }
        except requests.exceptions.ConnectionError as e:
            log.error(f"Connection error: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            return {
                "role": "assistant",
                "content": f"[LLM Error: Connection failed]",
                "tool_calls": None,
                "finish_reason": "error",
            }
        except Exception as e:
            log.error(f"Request error: {e}")
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

    # ── 3. 流式解析 SSE ──
    content_parts = []
    tool_calls_map: dict[int, dict] = {}  # index -> {id, name, arguments}
    finish_reason = None

    # 强制 UTF-8 解码，防止中文乱码
    resp.encoding = "utf-8"
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if not line.startswith("data: "):
            continue

        data_str = line[6:]  # 去掉 "data: " 前缀
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

        # 收集文本
        if delta.get("content"):
            print(delta["content"], end="", flush=True)
            content_parts.append(delta["content"])

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

        # 收集结束原因
        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]

    if content_parts:
        print()  # 换行

    # ── 4. 构造返回 ──
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
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
            )

    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
        "finish_reason": finish_reason,
    }


# ── 非流式调用（用于简单场景）────────────────────────


def chat(
    client: Config,
    model: str,
    system: str,
    user: str,
    max_retries: int = 3,
) -> str | None:
    """
    非流式调用，用于简单的单轮请求（如标题生成、摘要）。
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {client.api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                client.endpoint,
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return None
        except requests.exceptions.HTTPError as e:
            status = resp.status_code if resp is not None else None
            if status == 429:
                wait = 2 ** (attempt + 1)
                log.warning(f"Rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            log.error(f"HTTP error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
        except Exception as e:
            log.error(f"Error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)

    return None
