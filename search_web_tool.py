"""
自定义工具示例：search_web —— 网页搜索工具

这个文件演示如何为 Mini-OpenCode 添加一个**自定义工具**。
它是 docs/09-hands-on.md 教程的配套代码。

实现方式：
  使用 requests 调用搜索 API，将结果格式化后返回给 LLM。
  支持多个搜索后端：
    1. DuckDuckGo HTML 搜索（默认，无需 API Key）
    2. 可扩展为 Google/Bing 等（需 API Key）

注册方式：
  在 main.py 中 import 此模块即可（模块级代码自动注册）。

教学要点：
  - 展示如何用 tool.define() 注册自定义工具
  - 展示如何处理外部 HTTP 请求
  - 展示如何格式化结果供 LLM 消费
  - 展示错误处理和超时保护
"""

from __future__ import annotations
import re

import requests

import tool


# ── 搜索实现 ──────────────────────────────────────────


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

    resp = requests.post(url, data=params, headers=headers, timeout=15)
    resp.raise_for_status()
    html = resp.text

    # 简单正则解析搜索结果（教学用途，生产环境建议用 BeautifulSoup）
    results = []

    # DuckDuckGo HTML 搜索结果的结构:
    #   <a rel="nofollow" class="result__a" href="...">Title</a>
    #   <a class="result__snippet" href="...">Snippet text...</a>
    pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        r".*?"
        r'class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        if len(results) >= max_results:
            break

        raw_url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

        # DuckDuckGo 的链接是重定向 URL，尝试提取真实 URL
        real_url = raw_url
        url_match = re.search(r"uddg=([^&]+)", raw_url)
        if url_match:
            from urllib.parse import unquote

            real_url = unquote(url_match.group(1))

        if title:
            results.append(
                {
                    "title": title,
                    "url": real_url,
                    "snippet": snippet,
                }
            )

    return results


# ── 格式化输出 ────────────────────────────────────────


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


# ── 工具执行函数 ──────────────────────────────────────


async def _search_web(params: dict, ctx: tool.ToolContext) -> str:
    """
    搜索网页。这是 tool.define() 需要的 execute 函数。

    参数:
      query:       搜索关键词
      max_results: 最多返回几条结果（默认 5）
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


# ── 注册工具 ──────────────────────────────────────────
#
# 关键点：调用 tool.define() 就完成了注册。
# 只要在 main.py 中 import 本模块，工具就自动可用。

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
