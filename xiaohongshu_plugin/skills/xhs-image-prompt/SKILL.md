---
name: xhs-image-prompt
description: 小红书配图 AI 提示词生成指南：MidJourney/SD 提示词模板、小红书视觉审美规范、封面图设计原则
---

# 小红书 AI 配图提示词指南

## 一、小红书图片基本规范

### 尺寸要求
| 类型 | 比例 | 像素 | 说明 |
|------|------|------|------|
| **竖版（推荐）** | 3:4 | 1080×1440 | 信息流占比最大，曝光最优 |
| 方版 | 1:1 | 1080×1080 | 适合产品展示 |
| 横版 | 4:3 | 1440×1080 | 不推荐，信息流中偏小 |

### 图片数量建议
- **最佳**：6-9 张（内容丰富感）
- **最少**：3 张（太少显得单薄）
- 第 1 张 = 封面图（决定点击率）
- 第 2-9 张 = 内容图（决定收藏率）

## 二、小红书视觉审美偏好

### 主流风格和适用场景

**1. 清新自然风**
- 适合：美食、旅行、日常穿搭
- 关键词：natural lighting, soft pastel tones, airy, fresh
- 色调：低饱和度暖色、奶油色系

**2. 高级质感风**
- 适合：护肤、彩妆、奢品
- 关键词：studio lighting, editorial, luxury, muted tones
- 色调：莫兰迪色系、黑金配色

**3. 温馨日常风**
- 适合：家居、母婴、美食
- 关键词：warm lighting, cozy, lifestyle, candid
- 色调：暖黄、木质色

**4. 氛围感风**
- 适合：咖啡、书店、旅行
- 关键词：moody, cinematic, bokeh, golden hour
- 色调：电影感调色

**5. 极简风**
- 适合：数码、文具、生活方式
- 关键词：minimalist, white space, clean, geometric
- 色调：黑白灰、低饱和度

## 三、MidJourney 提示词模板

### 通用结构

```
[主体描述], [风格修饰], [光线描述], [构图说明],
[色调方向], [画质要求] --ar 3:4 --v 6 --style raw
```

### 封面图模板

```
A [形容词] photograph of [主体],
[视觉风格] aesthetic,
[光线]lighting, [构图] composition,
eye-catching, social media cover worthy,
high resolution, professional quality
--ar 3:4 --v 6 --style raw
```

示例：
```
A stunning flat lay photograph of autumn camping gear,
warm cozy aesthetic, golden hour natural lighting,
overhead composition with negative space for text,
earth tones, high resolution, professional quality
--ar 3:4 --v 6 --style raw
```

### 内容图模板

```
A detailed [角度] shot of [主体],
[风格] style, [光线] lighting,
lifestyle context, [情绪] mood,
high resolution, sharp focus
--ar 3:4 --v 6
```

### 常用修饰词

**光线**：
- natural lighting（自然光）
- golden hour lighting（黄金时段光）
- soft diffused lighting（柔和散射光）
- studio lighting（影棚光）
- backlit（逆光）

**构图**：
- flat lay（俯拍平铺）
- close-up detail shot（特写）
- over-the-shoulder（过肩拍）
- centered composition（居中构图）
- rule of thirds（三分法构图）

**情绪**：
- warm and inviting（温暖邀请感）
- clean and fresh（干净清新）
- luxurious and elegant（奢华优雅）
- playful and colorful（活泼多彩）

## 四、Stable Diffusion 提示词模板

### 正向提示词结构

```
[主体描述], [风格], [光线], [构图],
[色调], masterpiece, best quality,
ultra-detailed, sharp focus, 8k
```

### 反向提示词（通用）

```
low quality, blurry, distorted, watermark,
text, logo, signature, out of frame,
ugly, deformed, disfigured, oversaturated,
underexposed, overexposed
```

### 权重调节技巧
- 重要元素加权：`(camping tent:1.3)`
- 弱化元素降权：`(people:0.5)`
- 强调风格：`(minimalist:1.4)`

## 五、封面图设计原则

### 封面图必须做到

1. **3 秒法则**：缩略图状态下 3 秒内传达主题
2. **文字预留**：留出 1/4-1/3 的空间放标题文字
3. **色彩对比**：主体和背景有明显对比
4. **主体清晰**：一眼能看出拍的是什么
5. **情绪感染**：传达出一种令人向往的氛围

### 封面图常见错误
- ❌ 太杂乱，看不出重点
- ❌ 颜色太暗，缩略图看不清
- ❌ 没有留白，无法加文字
- ❌ 和内容不符，标题党

## 六、全套配图方案模板

```
### 封面图（第 1 张）
- 类型：[产品平铺/人物/场景]
- 要求：醒目、有文字空间
- 提示词：...

### 细节图（第 2-3 张）
- 类型：产品特写/使用场景
- 要求：展示核心卖点
- 提示词：...

### 过程图（第 4-6 张）
- 类型：步骤展示/对比效果
- 要求：信息清晰
- 提示词：...

### 氛围图（第 7-8 张）
- 类型：生活场景/使用感受
- 要求：营造代入感
- 提示词：...

### 总结图（第 9 张）
- 类型：合集/对比/总结
- 要求：收藏价值
- 提示词：...
```
