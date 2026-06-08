# aping-skills：5 个本地视频剪辑工具

> 仿王建硕 `claude-skills` 的命名和结构，用 **m3** 调度 + 本机已有工具实现。
> 命名约定：`aping-*` 前缀 + 动词（transcribing / regrouping / burning / dubbing / segmenting）。

## 🎯 设计原则

1. **判断交给 m3，执行交给脚本**——话题边界、AI 润色由 m3 做；切割、烧字幕、拼接由 Python 做
2. **一次 ffmpeg 编码**（aping-burning）——不级联重编码，画质零损失
3. **重编码切割**（aping-segmenting）——避免流复制导致的字幕/声音不同步
4. **共享库 aping-common**——统一 ffmpeg 路径、Windows 字体、SRT 解析

## 📦 5 个 skill 速查

| Skill | 用途 | 入口 |
|------|------|------|
| `aping-transcribing-audio` | 视频/音频 → SRT | `python aping-transcribing-audio/scripts/transcribe.py video.mp4 --language zh` |
| `aping-regrouping-srt` | 标点重切 + AI 润色 | `python aping-regrouping-srt/scripts/regroup.py sub.srt --mode polish` |
| `aping-burning-subtitles` | 烧字幕到视频 | `python aping-burning-subtitles/scripts/burn.py video.mp4 --srt sub.srt --out final.mp4` |
| `aping-dubbing-video` | 视频配音 | `python aping-dubbing-video/scripts/dub.py video.mp4 --srt sub.srt --voice zh-CN-XiaoxiaoNeural` |
| `aping-segmenting-video` | 长视频 → 多条短片 | `python aping-segmenting-video/scripts/segment.py video.mp4 --segments segments.json --out output/` |

## 🛠 完整流水线

```bash
# 1. 转录
python aping-transcribing-audio/scripts/transcribe.py input.mp4 --language zh

# 2. 重切 + AI 润色
python aping-regrouping-srt/scripts/regroup.py input.srt --mode polish

# 3. m3 读 SRT 决定 segments.json（手动对话）
#    "请把这段 SRT 切成 4 条独立短视频，给 JSON"

# 4. 切割
python aping-segmenting-video/scripts/segment.py input.mp4 \
    --segments segments.json \
    --srt input.srt \
    --out output/

# 5. 给每个 clip 烧字幕
for f in output/clip_*.mp4; do
    srt="${f%.mp4}.srt"
    python aping-burning-subtitles/scripts/burn.py "$f" \
        --srt "$srt" --out "${f%.mp4}.burned.mp4"
done

# 6. (可选) 配音
python aping-dubbing-video/scripts/dub.py input.mp4 \
    --srt input.zh.srt \
    --voice zh-CN-XiaoxiaoNeural \
    --out input.dub.mp4
```

## 📚 设计参考

- 王建硕 [jianshuo/claude-skills](https://github.com/jianshuo/claude-skills) — 原始 skill 设计和命名风格
- [whisperX](https://github.com/m-bain/whisperX) — 词级时间戳 + 说话人分离
- [MoviePy](https://github.com/Zulko/moviepy) — Python 视频编辑
- [edge-tts](https://github.com/rany2/edge-tts) — 微软神经 TTS
- [VoxCPM](https://github.com/openbmb) — OpenBMB 本地 TTS
- [mmx-cli](https://github.com/MiniMax/mmx-cli) — MiniMax 多模态 CLI

## 🐛 已知问题

- bash 控制台中文乱码（GBK 编码问题，**不影响文件**）
- `aping-dubbing-video` 完整跑没测过（您机器上 VoxCPM 已有，但 mmx 和 edge-tts 联调没测）
- `aping-transcribing-audio` 没在真实长视频上测过（只 import 测试过）

## ✅ 已验证

- `aping-common` 全部工具函数
- `aping-burning-subtitles` 真烧字幕（蓝底 + 微软雅黑 + 3 条字幕）
- `aping-segmenting-video` 真切割（5 秒视频 + 抽帧 + SRT 切片）
