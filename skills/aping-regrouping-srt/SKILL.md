---
name: aping-regrouping-srt
description: 把现有 SRT 重新切分（按标点）和 AI 润色错别字。不动时间戳、不改专有名词、cue 数量不变（修正模式）。可选合并模式把短 cue 拼成更长的段落。触发词："重切字幕"、"切分 SRT"、"润色字幕"、"标点重切"、"fix subtitles"。
---

# aping-regrouping-srt

SRT 标点重切 + AI 润色错别字。

## 两种模式

### 模式 A：AI 修正错别字（**默认**，时间戳不变）

```bash
python scripts/regroup.py input.srt --mode polish
```

行为：
- ✅ 修正"意数→总数"、"虚求→需求"等明显错别字
- ✅ 修正按上下文能 100% 确定的同音别字
- ❌ **不动时间戳、cue 数量、cue 边界**
- ❌ **不修改人名/品牌/产品名**（静默猜名字是大忌："黄一孟"→"黄一梦"）
- ❌ **不润色语序、删除重复、压缩内容**

### 模式 B：按标点重切

```bash
python scripts/regroup.py input.srt --mode regroup
```

行为：
- 把长 cue 按句号/问号/感叹号切开
- 软标点（逗号/分号）只在累计够长时切
- 单条字幕控制在 18 字符内（1080×1920 竖屏 FontSize=12 的安全值）
- 不动文本内容

## 何时不用

- 时间戳本身不准 → 用 `aping-transcribing-audio` 重新转录
- 需要翻译 → 用专门的翻译 skill（在规划中）
