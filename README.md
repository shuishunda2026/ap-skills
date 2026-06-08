# ap-skills

我自己（[shuis](https://github.com/shuishunda2026)）日常在 [pi](https://github.com/earendil-works/pi) 里用的 5 个视频剪辑 skill。

> 仿 [王建硕 claude-skills](https://github.com/jianshuo/claude-skills) 的命名和设计风格。
> 命名约定：`aping-` 前缀 + **动名词（V-ing）** 开头 —— `transcribing-audio` / `dubbing-video` / `burning-subtitles` —— 描述「正在做什么动作」。

## 这些 skill 是什么？

pi 的 skill 是一个带 frontmatter 的 `SKILL.md` 文件 + 一组脚本。当用户请求匹配 skill 描述里的**触发词**（「转写视频」「做 SRT」「烧字幕」……）时，pi 会自动加载这个 skill 并按里面写的流程执行。

装好后用触发词自然说话（如「转写这个视频」），或用斜杠命令 `/aping-transcribing-audio` 显式调用。**不需要重启 pi**，技能即时生效。

## 命名约定 / Naming

| 部分 | 规则 | 例子 |
|------|------|------|
| 前缀 | 永远是 `aping-` | `aping-...` |
| 动作 | 必须是 V-ing 动名词 | `transcribing`、`burning`、`dubbing` |
| 对象 | 媒体类型 | `audio`、`video`、`srt` |
| 分隔 | 用连字符 `-` | `aping-burning-subtitles` |

每个 skill 做**一件事**且只做一件，**可以单独调用，也可以串成流水线**。

---

## 安装 / Install

### 前置依赖

**必装**：
- Python 3.10+（已加 PATH）
- ffmpeg / ffprobe（已加 PATH）
- 微软雅黑或黑体（Windows 自带）

**Python 包**：
```bash
pip install whisperx faster-whisper moviepy edge-tts
```

**可选**：
- 中文更准的 ASR：`pip install funasr modelscope`（首次跑会下 1GB 模型）
- TTS 多音色：`npm i -g @MiniMax/mmx-cli`
- 本地克隆：装 `voxcpm`

### 方式 1：Git 克隆（推荐）

```bash
# 克隆
git clone https://github.com/shuishunda2026/ap-skills.git

# 同步到 pi agent 目录
xcopy /E /I /Y ap-skills %USERPROFILE%\.pi\agent\skills\ap-skills

# 重启 pi，5 个 skill 自动生效
```

### 方式 2：作为 pi 软链

```bash
git clone https://github.com/shuishunda2026/ap-skills.git D:\PIproject\skills
cmd //c "D:\PIproject\skills\sync-to-pi.bat"
```

### 方式 3：单文件调用

不通过 pi，直接命令行：
```bash
git clone https://github.com/shuishunda2026/ap-skills.git
cd ap-skills
python aping-transcribing-audio/scripts/transcribe.py my-video.mp4 --language zh
```

---

## 设计原则 / Design Philosophy

1. **m3 做判断，Python 做执行** — 话题边界、AI 润色由 m3 决定；切割、烧字幕、对齐由 Python 完成
2. **一次 ffmpeg 编码**（烧字幕）— 不级联重编码，画质零损失
3. **重编码切割** — 避免流复制导致的字幕/声音不同步
4. **共享库 `aping-common`** — 统一 ffmpeg 路径、Windows 字体、SRT 解析、控制台 UTF-8
5. **静默失败为零** — 任何步骤出错，stderr 必能直接 grep 出来

---

## Skills 总览 / Skills Overview

| Skill | 一句话作用 | 输入 → 输出 |
|---|---|---|
| [`aping-transcribing-audio`](./aping-transcribing-audio/) | 音视频转字幕（源语言） | 视频/音频 + 源语言 → SRT |
| [`aping-regrouping-srt`](./aping-regrouping-srt/) | SRT 标点重切 + AI 润色 | 旧 SRT → 重切 / 润色 SRT |
| [`aping-burning-subtitles`](./aping-burning-subtitles/) | 烧字幕到视频 | 视频 + SRT → 烧好字幕的 MP4 |
| [`aping-dubbing-video`](./aping-dubbing-video/) | 视频配音（多 TTS 引擎） | 视频 + SRT + voice ID → 配音视频 |
| [`aping-segmenting-video`](./aping-segmenting-video/) | 长视频按话题切片 | 长视频 + SRT + 切点 JSON → 多个独立短片 |

`aping-common/` 是**共享库**（无 SKILL.md，不暴露为 skill），被上面 5 个引用。

---

## 1. 转写 / Transcribe

### [`aping-transcribing-audio`](./aping-transcribing-audio/)

视频 / 音频 → 源语言 SRT。

- **中文默认走 FunASR paraformer-zh** —— 比 whisperx 错别字少 80%、速度快 8 倍、自动加标点
- 其它语言走 whisperx small（medium 兜底）
- 字级时间戳 + 标点重切，避免句子被切到一半
- `--engine {auto,funasr,whisperx}` 手动覆盖

> 触发词：`转写这个视频` / `做 SRT` / `出字幕` / `speech to text` / `出逐字稿`

### [`aping-regrouping-srt`](./aping-regrouping-srt/)

把一段 SRT 重新切 / 润色。

- **3 步断句法**（王建硕式）：① 拼合 → ② 累计时长/字符 → ③ 标点比例切
- **`polish` 模式**：让 m3 修正错别字（不动时间戳 / cue 边界 / 人名 / 数字 / 量词）
- **`ai` 模式**：让 m3 整段重切（必须 100% 覆盖原文本 + start/end 必从原 cue 选）

> 触发词：`重切这段字幕` / `AI 润色字幕` / `改断句` / `改错别字`

---

## 2. 烧字幕 / Burn Subtitles

### [`aping-burning-subtitles`](./aping-burning-subtitles/)

本地化流水线的终点。一次 ffmpeg 编码同时做：烧字幕（libass）。

- **不级联** —— 一次编码完成
- 自动用 Windows 微软雅黑（msyh）渲中文字幕
- 字幕样式：黑字 + 蓝底 + 16pt 字号
- 输出 H.264/AAC MP4，720p 同原片

> 触发词：`烧字幕` / `硬字幕` / `把字幕烧进视频` / `burn subtitles`

---

## 3. 配音 / Dub

### [`aping-dubbing-video`](./aping-dubbing-video/)

视频 + SRT + voice ID → 配好音的视频。

- **3 个 TTS 引擎自动路由**（按 voice ID 前缀）：
  - `zh-CN-*` / `en-*-Neural` → **edge-tts**（微软免费）
  - `zh_*_bigtts` → **VoxCPM**（本地克隆 / 情感）
  - `mmx:*` → **mmx**（MiniMax 平台多音色）
- **时长对齐策略**：太短补静音（不拉伸 - 拉伸会变声）；太长 atempo 加速（最低 0.82x）
- `--sample 3` 先试听 3 条，再全片配音

> 触发词：`配音` / `中文配音` / `dub video` / `TTS 这段字幕` / `换语言旁白`

---

## 4. 切片 / Segment

### [`aping-segmenting-video`](./aping-segmenting-video/)

长访谈 / 讲座 / 播客 → 3–6 段独立可看的短片。

- **重编码切割**（避免流复制音画不同步）
- 给每个 clip 抽 1 帧作为缩略图
- SRT 归零（`00:00:00,000`）让每个 clip 独立字幕
- 切点由 m3 给的 `segments.json` 决定（不是脚本自己猜）

> 触发词：`按话题切视频` / `拆条` / `切短片` / `切成 3 段独立短视频`

---

## ASR / TTS 引擎选型

### ASR

| 语言 | 默认引擎 | 备选 | 命令 |
|------|---------|------|------|
| 中文 | **FunASR paraformer-zh** | whisperx small | `--engine funasr` 或 `--engine whisperx` |
| 英文 | whisperx small | FunASR（需指定英文模型） | `--engine whisperx` |
| 日/韩 | whisperx | - | `--engine whisperx --language ja` |

**FunASR vs whisperx small**（中文 26s 测试）：

| 指标 | whisperx small | **FunASR** |
|------|---------------|-----------|
| 错别字 | 2-3 / 段 | **0** |
| 自动加标点 | ❌ | ✅ |
| 推理速度 | 30s | **3.7s（8× 快）** |
| 模型大小 | 460MB | ~1GB（一次性） |

### TTS

| 引擎 | 命令 | 适用 |
|------|------|------|
| **edge-tts** | `--voice zh-CN-XiaoxiaoNeural` | 微软免费中文/英文 |
| **mmx** | `--voice mmx:female-shaonv` | MiniMax 平台多音色 |
| **voxcpm** | `--voice zh_xxx_bigtts` | 本地克隆特定人声 |

---

## 典型工作流串接

**完整口播视频 → 5 条短片 + 烧字幕 + 配音：**

```
源视频 (口播.mp4)
  └─ aping-transcribing-audio         → 口播.srt (FunASR 3.7s)
      └─ aping-regrouping-srt --mode polish → 口播.polished.srt (m3 润色)
          │  [m3 读 SRT 决定 segments.json]
          └─ aping-segmenting-video   → output/clip_01_*.mp4 + .srt + .jpg
              └─ aping-burning-subtitles → output/clip_*.burned.mp4
                  └─ aping-dubbing-video  → output/clip_*.dubbed.mp4
```

**纯转写+烧字幕**（不上 AI / 不切片）：

```
video.mp4
  └─ aping-transcribing-audio   → video.srt
      └─ aping-burning-subtitles → video.burned.mp4
```

**单条配音**（已有 SRT）：

```
video.mp4 + en.srt
  └─ aping-dubbing-video --voice en-US-AriaNeural → video.dubbed.mp4
```

---

## 性能数据 / Performance

测试视频：`D:/PIproject/test.mp4` (26.77s, 720×1280, HEVC+AAC)

| 阶段 | 时间 | 引擎 |
|------|------|------|
| 转录 | **3.7s** | FunASR paraformer-zh |
| mmx 润色 SRT | ~5s | m3 (3 cue) |
| 切片 | 2.2s | ffmpeg 重编码 |
| 抽帧 | 0.3s | ffmpeg |
| 烧字幕 | 4.5s | ffmpeg libass |
| 配音 | 2.1s | edge-tts 小晓 |
| **总时长** | **~18s** | - |

---

## 🐛 已知问题 / Known Issues

- **Windows bash 控制台中文乱码**：`aping-common` 已修（`setup_console()`），脚本输出不乱码
- **长视频没测过**：所有 skill 都只验过 26s 短视频
- **`aping-dubbing-video` VoxCPM 没测**：需要找一段参考音频

## 🆘 故障排查

**ffmpeg 找不到**：
```bash
where ffmpeg     # Windows
# 解决：装 ffmpeg 并加到 PATH，或改 aping-common/aping_common.py 的 candidates
```

**FunASR 模型下载慢**：
```bash
# Linux/macOS
export MODELSCOPE_CACHE=/path/to/cache
# Windows
set MODELSCOPE_CACHE=D:\modelscope_cache
```

**mmx 命令找不到**：
```bash
where mmx.cmd
# 解决：npm i -g @MiniMax/mmx-cli
```

**烧字幕乱码**：检查 `C:\Windows\Fonts\msyh.ttc` 是否存在（微软雅黑）

---

## 贡献 / Contributing

新增 skill 的要求：

1. 目录名用 **V-ing 动名词**（如 `aping-doing-something`），加 `aping-` 前缀
2. 目录内放 `SKILL.md`，frontmatter 里写 `name` 和 `description`（含具体触发词/例句）
3. 需要的脚本放同目录下，共享工具放 `aping-common/`
4. 提 PR，在 PR 描述里说明 skill 用途和触发词

---

## 相关链接

- GitHub: https://github.com/shuishunda2026/ap-skills
- pi 文档: https://github.com/earendil-works/pi
- 王建硕原版: https://github.com/jianshuo/claude-skills
