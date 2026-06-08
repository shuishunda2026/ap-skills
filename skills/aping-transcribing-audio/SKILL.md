---
name: aping-transcribing-audio
description: 把视频或音频转成源语言 SRT 字幕。中文用 whisperx（OpenAI Whisper + 词级对齐），输出按标点切分的干净 SRT。触发词："转写这个视频"、"做字幕"、"转成 SRT"、"speech to text"、"出逐字稿"。
---

# aping-transcribing-audio

音视频 → 源语言 SRT。

底层工具：`whisperx`（OpenAI Whisper + 强制对齐）。

## 使用方式

```bash
# 命令行
python scripts/transcribe.py input.mp4 --language zh

# 带参数
python scripts/transcribe.py input.mp4 \
    --language zh \
    --model large-v2 \
    --device cpu \
    --compute_type int8 \
    --output output/transcript.srt
```

## 关键设计

- **必传 `--language`**：永不自动检测（避免中→日、西→葡的误判）
- **CPU 默认走 `int8` 量化**：速度比 float32 快 4 倍，精度损失 < 1%
- **输出按标点切**：避免一条字幕太长被切到一半

## 何时不用这个 skill

- 已有 SRT → 直接用 `aping-regrouping-srt` 重切即可
- 需要翻译成其他语言 → 转录后再用 `aping-burning-subtitles` 的姊妹流程
- 长视频（> 2 小时）→ 先用 `aping-segmenting-video` 切段再逐段转录

## 下游

- `aping-regrouping-srt` — 标点重切 + AI 润色错别字
- `aping-burning-subtitles` — 烧字幕到视频
- `aping-dubbing-video` — 配其他语言旁白
