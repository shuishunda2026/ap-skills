---
name: aping-dubbing-video
description: 给视频配上新语言的旁白（dub）。按 voice ID 路由 TTS 引擎：edge-tts 用于英文/多语种/免费场景；VoxCPM 用于中文本地克隆/情感。逐条字幕单独合成，按时间戳拼接，对齐原视频时长。触发词："配音"、"中文配音"、"dub video"、"TTS 这段字幕"、"换语言旁白"。
---

# aping-dubbing-video

视频 + 目标语言 SRT → 配音视频。

## 引擎选择

按 voice ID 路由：

| Voice ID 模式 | 引擎 | 用途 |
|------------|-----|------|
| `zh-CN-*Neural` | edge-tts | 中文（免费、标准） |
| `en-US-*Neural` | edge-tts | 英文（免费、自然） |
| `zh_*_bigtts` | VoxCPM | 中文（情感、可克隆） |
| `mmx:*` | mmx CLI | MiniMax 平台音色 |

## 使用方式

```bash
# 用 edge-tts 默认中文女声配音
python scripts/dub.py video.mp4 --srt sub.zh.srt --voice zh-CN-XiaoxiaoNeural

# 用 VoxCPM 克隆特定人声
python scripts/dub.py video.mp4 --srt sub.zh.srt --voice zh_female_xxx_bigtts --tool voxcpm

# 调整语速（edge-tts）
python scripts/dub.py video.mp4 --srt sub.zh.srt --voice zh-CN-XiaoxiaoNeural --rate "-8%"
```

## 三档时长对齐策略

每条字幕 TTS 后 vs 原 SRT 时长对比：

| 情况 | 处理 |
|-----|------|
| TTS 时长 = 目标时长 | 直接用 |
| TTS 时长 > 目标时长 | 用 atempo 滤镜加速到 0.82-1.0x |
| TTS 时长 < 目标时长 | 先 atempo 拉伸到 0.95x，再补静音 |

**下限 0.82x**——再低声音会"像嗑药"。

## 调试流程

```bash
# 1. 先 sample 3-5 段试听（合成前 3 条字幕）
python scripts/dub.py video.mp4 --srt sub.srt --voice zh-CN-XiaoxiaoNeural --sample 3

# 2. 听样音，调 voice/rate/pitch
# 3. 全片配音
python scripts/dub.py video.mp4 --srt sub.srt --voice zh-CN-XiaoxiaoNeural --out dub.mp4
```
