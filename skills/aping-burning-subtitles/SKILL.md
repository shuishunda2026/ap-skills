---
name: aping-burning-subtitles
description: 把 SRT 字幕烧进视频画面（libass 硬字幕，微信/抖音/小红书等播放器能直接显示）。同时支持混入配音轨、保留原声作背景。一次 ffmpeg 编码完成所有操作，**不级联重编码**，画质零损失。触发词："烧字幕"、"硬字幕"、"burn subtitles"、"加字幕"、"字幕嵌入视频"、"混配音"。
---

# aping-burning-subtitles

视频 + SRT [+ 可选配音] → 烧好字幕的成片。

## 核心原则

> **一次 ffmpeg 编码完成所有操作**——不级联（避免画质损失）。
> 这是王建硕 `wjs-burning-subtitles` 的核心思想。

## 三种工作模式

```bash
# 1. 仅烧字幕
python scripts/burn.py video.mp4 --srt sub.srt --out final.mp4

# 2. 烧字幕 + 混入配音轨
python scripts/burn.py video.mp4 --srt sub.srt --dub dub.mp4 --out final.mp4

# 3. 仅混配音（不烧字幕）
python scripts/burn.py video.mp4 --dub dub.mp4 --out final.mp4 --no-burn
```

## 字号/字体经验值（Windows 1080×1920 竖屏）

| FontSize | 中文渲染宽度 | 适用场景 |
|----------|------------|---------|
| 12 | ~30-35 px | **推荐默认**（一行 15 字内） |
| 14 | ~36-40 px | 较紧凑 |
| 16 | ~42-45 px | 容易溢出，需缩 margin |
| 22 | ~55+ px | 经常溢出，不推荐 |

## 调试流程（必看）

烧字幕是**不可逆重编码**，调试流程：

```bash
# Step 1: 先烧 30s 试看
python scripts/burn.py video.mp4 --srt sub.srt --out test.mp4 --preview 30

# Step 2: 抽一帧看字号是否合适
ffmpeg -ss 15 -i test.mp4 -frames:v 1 frame.png

# Step 3: 用户/自己看图 → 调字号/字体 → 再 30s 试

# Step 4: 满意后跑全片
python scripts/burn.py video.mp4 --srt sub.srt --out final.mp4
```

## 配音混音参数

- 原声降为 `0.18` (~−15 dB) 作背景，听到人声呼吸/笑声
- 配音 `1.0` 全音量
- `normalize=0` 防止 amix 自动衰减

## 字体

Windows 默认用 `msyh`（微软雅黑）。如果机器没装，fallback 到 `simhei`（黑体）。
