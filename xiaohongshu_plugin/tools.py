"""
小红书专用工具 —— 通过 tool.define() 注册到全局工具表

工具列表：
  1. xhs_tags         生成小红书热门标签
  2. xhs_format       格式化笔记排版
  3. xhs_review       内容质量评分
  4. xhs_image_prompt  生成 AI 配图提示词
"""

from __future__ import annotations
import re

import tool

# 记录本模块注册的工具名，供 __init__.py 统计
_TOOL_NAMES: list[str] = []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具 1：标签生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 小红书热门分类标签库
_TAG_LIBRARY = {
    "美妆": [
        "#美妆",
        "#护肤",
        "#化妆教程",
        "#好物推荐",
        "#平价好物",
        "#学生党",
        "#素颜",
        "#防晒",
        "#面膜",
        "#精华",
        "#美白",
        "#抗老",
        "#敏感肌",
    ],
    "穿搭": [
        "#穿搭",
        "#ootd",
        "#日常穿搭",
        "#通勤穿搭",
        "#穿搭分享",
        "#显瘦穿搭",
        "#小个子穿搭",
        "#大码穿搭",
        "#韩系穿搭",
        "#简约风",
        "#氛围感穿搭",
    ],
    "美食": [
        "#美食",
        "#食谱",
        "#家常菜",
        "#烘焙",
        "#减脂餐",
        "#下饭菜",
        "#懒人菜",
        "#空气炸锅",
        "#一人食",
        "#探店",
        "#咖啡",
    ],
    "旅行": [
        "#旅行",
        "#旅游攻略",
        "#拍照",
        "#打卡",
        "#周末去哪",
        "#小众景点",
        "#自驾游",
        "#露营",
        "#citywalk",
        "#旅行日记",
    ],
    "家居": [
        "#家居",
        "#装修",
        "#收纳",
        "#好物分享",
        "#租房改造",
        "#ins风",
        "#极简生活",
        "#家居好物",
        "#软装",
        "#居家",
    ],
    "数码": [
        "#数码",
        "#科技",
        "#手机",
        "#电脑",
        "#iPad",
        "#效率工具",
        "#App推荐",
        "#数码好物",
        "#学习方法",
        "#生产力",
    ],
    "健身": [
        "#健身",
        "#减肥",
        "#瘦身",
        "#运动",
        "#瑜伽",
        "#跑步",
        "#马甲线",
        "#增肌",
        "#减脂",
        "#打卡",
    ],
    "母婴": [
        "#母婴",
        "#育儿",
        "#宝宝",
        "#新手妈妈",
        "#辅食",
        "#早教",
        "#待产包",
        "#孕期",
        "#宝妈日常",
    ],
    "职场": [
        "#职场",
        "#工作",
        "#副业",
        "#自媒体",
        "#涨粉",
        "#运营",
        "#面试",
        "#简历",
        "#升职加薪",
        "#自律",
    ],
    "通用": [
        "#小红书",
        "#生活",
        "#日常",
        "#分享",
        "#经验",
        "#干货",
        "#必看",
        "#合集",
        "#种草",
        "#拔草",
        "#真实测评",
    ],
}


async def _xhs_tags(params: dict, ctx: tool.ToolContext) -> str:
    """生成小红书热门标签"""
    topic = params["topic"]
    count = params.get("count", 18)
    category = params.get("category", "")

    tags = []

    # 主题直接标签
    tags.append(f"#{topic}")

    # 按分类匹配
    matched_categories = []
    topic_lower = topic.lower()
    for cat, cat_tags in _TAG_LIBRARY.items():
        if cat in topic or category == cat:
            matched_categories.append(cat)
            tags.extend(cat_tags)

    # 如果没有匹配到分类，用通用标签
    if not matched_categories:
        tags.extend(_TAG_LIBRARY["通用"])
        # 尝试生成语义相关标签
        tags.extend(
            [
                f"#{topic}分享",
                f"#{topic}推荐",
                f"#{topic}攻略",
                f"#{topic}合集",
                f"#{topic}必看",
            ]
        )

    # 去重并截取
    seen = set()
    unique_tags = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique_tags.append(t)

    selected = unique_tags[:count]

    lines = [
        f"🏷️ 小红书标签推荐（主题: {topic}）",
        f"匹配分类: {', '.join(matched_categories) if matched_categories else '通用'}",
        "",
        "核心标签（前 5 个优先使用）：",
    ]
    for i, t in enumerate(selected[:5]):
        lines.append(f"  {i + 1}. {t}")

    lines.append("")
    lines.append("扩展标签：")
    for t in selected[5:]:
        lines.append(f"  {t}")

    lines.append("")
    lines.append(f"共 {len(selected)} 个标签")
    lines.append("")
    lines.append("标签组（可直接复制）：")
    lines.append(" ".join(selected))

    return "\n".join(lines)


tool.define(
    name="xhs_tags",
    description=(
        "为小红书笔记生成热门标签。根据主题和分类，从标签库中智能匹配"
        "核心标签和长尾标签，优化笔记的搜索曝光。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "笔记主题关键词，如 '露营' '通勤穿搭' '平价护肤'",
            },
            "count": {
                "type": "integer",
                "description": "生成标签数量（默认 18，建议 15-20）",
                "default": 18,
            },
            "category": {
                "type": "string",
                "description": "分类：美妆/穿搭/美食/旅行/家居/数码/健身/母婴/职场",
            },
        },
        "required": ["topic"],
    },
    execute=_xhs_tags,
)
_TOOL_NAMES.append("xhs_tags")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具 2：笔记格式化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _xhs_format(params: dict, ctx: tool.ToolContext) -> str:
    """将内容格式化为小红书标准笔记排版"""
    title = params["title"]
    body = params["body"]
    tags = params.get("tags", "")

    # 标题处理：确保有 emoji
    if not any(ord(c) > 0x1F600 for c in title):
        # 没有 emoji，自动添加
        title = f"✨ {title}"

    # 正文排版优化
    lines = body.split("\n")
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if line:
            formatted_lines.append(line)
        else:
            formatted_lines.append("")

    formatted_body = "\n".join(formatted_lines)

    # 标签处理
    if tags:
        tag_line = tags.strip()
    else:
        tag_line = "#小红书 #分享 #好物推荐"

    # 组装完整笔记
    note = []
    note.append("═" * 40)
    note.append("📝 小红书笔记预览")
    note.append("═" * 40)
    note.append("")
    note.append(f"【标题】{title}")
    note.append("")
    note.append("【正文】")
    note.append(formatted_body)
    note.append("")
    note.append("─" * 40)
    note.append(f"【标签】{tag_line}")
    note.append("─" * 40)
    note.append("")

    # 字数统计
    text_len = len(formatted_body.replace("\n", "").replace(" ", ""))
    title_len = len(title)
    tag_count = tag_line.count("#")

    note.append("📊 笔记数据：")
    note.append(
        f"  标题字数: {title_len} {'✅' if 8 <= title_len <= 20 else '⚠️ 建议8-20字'}"
    )
    note.append(
        f"  正文字数: {text_len} {'✅' if 300 <= text_len <= 800 else '⚠️ 建议300-800字'}"
    )
    note.append(
        f"  标签数量: {tag_count} {'✅' if 15 <= tag_count <= 20 else '⚠️ 建议15-20个'}"
    )

    return "\n".join(note)


tool.define(
    name="xhs_format",
    description=(
        "将笔记内容格式化为小红书标准排版。自动添加 emoji、优化排版、"
        "统计字数，并检查是否符合平台最佳实践。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "笔记标题",
            },
            "body": {
                "type": "string",
                "description": "笔记正文内容",
            },
            "tags": {
                "type": "string",
                "description": "标签字符串，如 '#露营 #户外 #周末'",
            },
        },
        "required": ["title", "body"],
    },
    execute=_xhs_format,
)
_TOOL_NAMES.append("xhs_format")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具 3：内容质量评分
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 小红书常见违禁词 / 敏感词（简化版）
_SENSITIVE_WORDS = [
    "最好",
    "第一",
    "绝对",
    "100%",
    "永远",
    "万能",
    "国家级",
    "驰名",
    "特供",
    "秒杀一切",
    "全网最低",
    "微信",
    "淘宝",
    "拼多多",
    "抖音",  # 引流词
    "加我",
    "私聊",
    "私信下单",
    "代购",
]


async def _xhs_review(params: dict, ctx: tool.ToolContext) -> str:
    """对小红书笔记进行质量评分"""
    title = params.get("title", "")
    body = params.get("body", "")
    tags = params.get("tags", "")

    full_text = f"{title}\n{body}\n{tags}"
    issues = []
    scores = {"compliance": 25, "quality": 25, "platform": 25, "engagement": 25}

    # ── 1. 合规性检查 ──
    found_sensitive = []
    for word in _SENSITIVE_WORDS:
        if word in full_text:
            found_sensitive.append(word)

    if found_sensitive:
        deduct = min(len(found_sensitive) * 5, 20)
        scores["compliance"] -= deduct
        issues.append(f"🔴 发现敏感词: {', '.join(found_sensitive)}")

    # ── 2. 文案质量 ──
    body_len = len(body.replace("\n", "").replace(" ", ""))
    title_len = len(title)

    # 标题检查
    if title_len < 8:
        scores["quality"] -= 5
        issues.append(f"🟡 标题过短 ({title_len}字)，建议 8-20 字")
    elif title_len > 25:
        scores["quality"] -= 3
        issues.append(f"🟡 标题过长 ({title_len}字)，建议 8-20 字")

    # 标题 emoji 检查
    has_emoji = any(ord(c) > 0x1F600 for c in title)
    if not has_emoji:
        scores["quality"] -= 3
        issues.append("🔵 标题缺少 emoji，建议添加以提高点击率")

    # 正文长度
    if body_len < 200:
        scores["quality"] -= 8
        issues.append(f"🟡 正文过短 ({body_len}字)，建议 300-800 字")
    elif body_len > 1000:
        scores["quality"] -= 3
        issues.append(f"🔵 正文偏长 ({body_len}字)，移动端阅读体验可能下降")

    # 段落检查
    paragraphs = [p for p in body.split("\n") if p.strip()]
    if len(paragraphs) < 3:
        scores["quality"] -= 5
        issues.append("🟡 段落过少，建议分 5-8 个段落增加可读性")

    # ── 3. 平台适配度 ──
    tag_count = tags.count("#")
    if tag_count < 10:
        scores["platform"] -= 8
        issues.append(f"🟡 标签过少 ({tag_count}个)，建议 15-20 个")
    elif tag_count > 25:
        scores["platform"] -= 3
        issues.append(f"🔵 标签过多 ({tag_count}个)，可能被判定为过度优化")

    # 开头钩子检查
    first_lines = body.strip().split("\n")[:2]
    first_text = " ".join(first_lines)
    if len(first_text) > 50:
        # 好的钩子
        pass
    else:
        scores["platform"] -= 5
        issues.append("🟡 开头两行较短，可能在信息流中不够吸引人")

    # ── 4. 互动潜力 ──
    # 检查互动引导
    interaction_words = [
        "吗？",
        "呢？",
        "你们",
        "评论区",
        "点赞",
        "收藏",
        "关注",
        "姐妹们",
        "宝子们",
        "你觉得",
    ]
    has_interaction = any(w in full_text for w in interaction_words)
    if not has_interaction:
        scores["engagement"] -= 8
        issues.append("🟡 缺少互动引导，建议在结尾加入提问或互动")

    # 检查是否有干货（收藏价值）
    value_patterns = [
        "步骤",
        "方法",
        "技巧",
        "清单",
        "攻略",
        "教程",
        "推荐",
        "合集",
        "对比",
        "总结",
    ]
    has_value = any(w in full_text for w in value_patterns)
    if not has_value:
        scores["engagement"] -= 5
        issues.append("🔵 可增加干货内容（步骤/清单/方法等），提高收藏率")

    # ── 汇总 ──
    total = sum(scores.values())

    # 评级
    if total >= 90:
        grade = "S 优秀"
    elif total >= 80:
        grade = "A 良好"
    elif total >= 65:
        grade = "B 合格"
    elif total >= 50:
        grade = "C 待改进"
    else:
        grade = "D 需大改"

    # 数据预估
    if total >= 85:
        est = "点赞 500-2000 | 收藏 300-1000 | 评论 50-200"
    elif total >= 70:
        est = "点赞 100-500 | 收藏 50-300 | 评论 20-50"
    elif total >= 55:
        est = "点赞 30-100 | 收藏 20-50 | 评论 5-20"
    else:
        est = "互动数据可能较低，建议先优化后发布"

    lines = [
        "═" * 40,
        "📋 小红书笔记质检报告",
        "═" * 40,
        "",
        "📊 评分明细：",
        f"  合规性:   {scores['compliance']}/25",
        f"  文案质量: {scores['quality']}/25",
        f"  平台适配: {scores['platform']}/25",
        f"  互动潜力: {scores['engagement']}/25",
        f"  ─────────────",
        f"  总分:     {total}/100  评级: {grade}",
        "",
    ]

    if issues:
        lines.append("⚠️ 问题清单：")
        for issue in issues:
            lines.append(f"  {issue}")
        lines.append("")

    if not issues:
        lines.append("✅ 未发现明显问题")
        lines.append("")

    lines.append("📈 互动数据预估：")
    lines.append(f"  {est}")

    return "\n".join(lines)


tool.define(
    name="xhs_review",
    description=(
        "对小红书笔记进行质量评分。检查合规性（敏感词/违规内容）、"
        "文案质量（标题/正文/排版）、平台适配度（标签/长度）、"
        "互动潜力（钩子/干货/引导），给出 0-100 分评级和改进建议。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "笔记标题",
            },
            "body": {
                "type": "string",
                "description": "笔记正文",
            },
            "tags": {
                "type": "string",
                "description": "标签字符串",
            },
        },
        "required": ["title", "body"],
    },
    execute=_xhs_review,
)
_TOOL_NAMES.append("xhs_review")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具 4：AI 配图提示词生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 小红书常见视觉风格映射
_STYLE_PRESETS = {
    "清新自然": "natural lighting, soft tones, fresh and clean aesthetic, minimal background",
    "高级质感": "studio lighting, luxury aesthetic, elegant composition, muted color palette, editorial style",
    "温馨日常": "warm cozy lighting, homey atmosphere, lifestyle photography, candid feel",
    "ins风": "instagram aesthetic, film grain, vsco filter look, trendy composition",
    "极简": "minimalist style, white space, clean lines, simple composition, Scandinavian design",
    "复古": "vintage aesthetic, retro color grading, film photography look, nostalgic mood",
    "氛围感": "moody atmosphere, cinematic lighting, bokeh background, dreamy feel",
}


async def _xhs_image_prompt(params: dict, ctx: tool.ToolContext) -> str:
    """生成小红书配图 AI 提示词"""
    subject = params["subject"]
    style = params.get("style", "清新自然")
    image_type = params.get("image_type", "封面图")
    count = params.get("count", 1)

    style_en = _STYLE_PRESETS.get(style, _STYLE_PRESETS["清新自然"])

    results = []
    results.append("═" * 40)
    results.append("🎨 小红书 AI 配图提示词")
    results.append("═" * 40)
    results.append("")
    results.append(f"主题: {subject}")
    results.append(f"风格: {style}")
    results.append(f"图片类型: {image_type}")
    results.append("")

    for i in range(count):
        label = f"图 {i + 1}" if count > 1 else image_type
        results.append(f"── {label} ──")
        results.append("")

        if image_type == "封面图" or (count > 1 and i == 0):
            # 封面图：需要更醒目
            prompt_en = (
                f"A visually striking photograph of {subject}, "
                f"{style_en}, "
                f"eye-catching composition, suitable for social media cover, "
                f"vertical aspect ratio 3:4, high resolution, "
                f"professional quality, trending on xiaohongshu"
            )
            prompt_cn = (
                f"一张关于「{subject}」的精美{style}风格照片，"
                f"构图醒目适合作为封面，竖版 3:4 比例，高清画质。"
            )
        else:
            # 内容图：展示细节
            prompt_en = (
                f"A detailed photograph showcasing {subject}, "
                f"{style_en}, "
                f"detail shot, lifestyle context, "
                f"vertical aspect ratio 3:4, high resolution"
            )
            prompt_cn = (
                f"一张关于「{subject}」的细节展示照片，"
                f"{style}风格，生活化场景，竖版 3:4 比例。"
            )

        results.append("中文描述：")
        results.append(f"  {prompt_cn}")
        results.append("")
        results.append("MidJourney 提示词：")
        results.append(f"  {prompt_en} --ar 3:4 --v 6 --style raw")
        results.append("")
        results.append("Stable Diffusion 提示词：")
        sd_prompt = prompt_en.replace(", trending on xiaohongshu", "")
        results.append(f"  正向: {sd_prompt}, masterpiece, best quality")
        results.append(f"  反向: low quality, blurry, distorted, watermark, text, logo")
        results.append("")

    results.append("─" * 40)
    results.append("💡 使用建议：")
    results.append("  - 小红书最佳图片比例为 3:4（竖版）")
    results.append("  - 封面图要在缩略图状态下仍然醒目")
    results.append("  - 建议 6-9 张图片组成一组")
    results.append("  - 保持整组图片风格统一")

    return "\n".join(results)


tool.define(
    name="xhs_image_prompt",
    description=(
        "为小红书笔记生成 AI 配图提示词。支持 MidJourney 和 Stable Diffusion 格式，"
        "可选择多种小红书流行视觉风格（清新自然/高级质感/温馨日常/ins风/极简/复古/氛围感），"
        "自动适配封面图和内容图的不同构图需求。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "拍摄/绘图主题，如 '秋日露营帐篷' '桌面咖啡拉花'",
            },
            "style": {
                "type": "string",
                "description": "视觉风格: 清新自然/高级质感/温馨日常/ins风/极简/复古/氛围感",
                "default": "清新自然",
            },
            "image_type": {
                "type": "string",
                "description": "图片类型: 封面图/内容图/全套（封面+内容）",
                "default": "封面图",
            },
            "count": {
                "type": "integer",
                "description": "生成数量（全套时建议 6-9）",
                "default": 1,
            },
        },
        "required": ["subject"],
    },
    execute=_xhs_image_prompt,
)
_TOOL_NAMES.append("xhs_image_prompt")
