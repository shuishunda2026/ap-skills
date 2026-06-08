# aping-skills 沉淀笔记

> 这套 skill 跑通后的关键决策、踩过的坑、未来的工作。
> 写给"三个月后回到这个项目的自己"。

---

## 🎬 完整流程（26s 短视频测试结果）

```
test.mp4 (26.77s, 720×1280, HEVC+AAC)
  │
  ▼ aping-transcribing-audio
  test.funasr.srt
  │   ① 3 段标点切分
  │   ② 0 错别字（whisper small 有 2-3 个）
  │   ③ 3.7s 推理（whisper small 要 30s）
  │
  ▼ aping-regrouping-srt --mode polish
  test.funasr.polished.srt
  │   mmx 确认 0 改（质量已经够好）
  │
  ▼ aping-segmenting-video
  clips_funasr/
    clip_01_skill-passed.{mp4, srt, jpg}
    clip_02_real-test.{mp4, srt, jpg}
  │
  ▼ aping-burning-subtitles
    clip_01_skill-passed.burned.mp4
    clip_02_real-test.burned.mp4
  │
  ▼ aping-dubbing-video（可选）
  test.dubbed.mp4（edge-tts 小晓 + 静音对齐）
```

---

## 🔑 关键决策

### 1. ASR 引擎：FunASR > whisperx small（中文）

| 指标 | whisperx small | **FunASR paraformer-zh** |
|------|---------------|-------------------------|
| 中文错别字 | 2-3 / 段 | **0** |
| 自动加标点 | ❌ | ✅（逗号 + 句号） |
| 推理速度 | 30s | **3.7s（8× 快）** |
| 模型大小 | 460MB | ~1GB（一次性下载） |
| GPU | 需要 wav2vec2 | **CPU 也能跑** |

**结论**：中文场景下 FunASR **完胜**。Whisper 只做英文 fallback。

### 2. 字幕断句：王建硕 3 步法的极简版

```python
# 核心思路（~50 行代码）:
# Step 1: FunASR text 已带标点
# Step 2: 强标点（。！？）→ 必切
# Step 3: 软标点（，；）→ 累计字数 ≥ max_chars 才切
```

**不要**用复杂的 word-level 对齐——FunASR 字级时间戳直接拿来用就行。

### 3. 时长对齐：atimepo 只加速，不拉伸

```
TTS 时长 8s，目标 6s（太长）→ atempo 1.33x 加速
TTS 时长 5s，目标 8s（太短）→ 补静音
```

**错误思路**：0.95x 拉伸——会变声。

### 4. ffmpeg libass 烧字幕：一次编码

`ffmpeg -vf "ass=...sub.srt"` 一次完成提取+烧录。**不要**先转码再烧。

### 5. 视频切割：必须重编码

`stream copy` 切割会让字幕比声音早 0.6-1.5s（解码边界问题）。**重编码** (`-c:v libx264 -c:a aac`) 才能保证音画同步。

---

## 🐛 踩过的坑（调试记录）

### 坑 1: Windows ffmpeg.EXE 大小写
- `shutil.which("ffprobe")` 在 PATH 里有 ffmpeg 时**找不到** ffprobe
- 解决：到 ffmpeg 同目录用 `os.listdir` 找 `ffprobe.exe`（不区分大小写）

### 坑 2: libass Windows 路径解析
- 路径含 `:` 误被解析成 "video size filter"
- 解决：路径加 `\\` 转义 → `ass='C\\:\\\\path\\\\to.srt'`

### 坑 3: Windows subprocess 退出码
- 报错 `exit status 2880417800`（-22 编码后）
- 解决：**别看 exit code**，看 stdout/stderr 实际报错

### 坑 4: ffmpeg 抽帧需要 `-update 1`
- `image2` 抽帧默认追加模式会失败
- 解决：`-update 1` 单帧模式

### 坑 5: 静音拼接 mp3 失败
- `anullsrc` 输出 flt 格式，concat mp3 失败
- 解决：分 3 步走——wav 静音 → concat → 重编 mp3

### 坑 6: bash 命令行 `-5%` 被吞
- bash 把 `%` 当作业控制符
- 解决：不在 shell 传含 `%` 的参数，或者写默认值

### 坑 7: 控制台中文乱码
- Windows 默认 GBK
- 解决：脚本入口 `sys.stdout.reconfigure(encoding="utf-8")`（共享库 `setup_console()`）

### 坑 8: junction 链接转义失败
- Git Bash 调 `cmd.exe //c mklink` 把 `\\` 当成转义
- 解决：**直接复制**而不是 junction 软链

---

## 🤖 m3 调度 + Python 执行的边界

| 任务 | 谁做 |
|------|------|
| 决定用哪个 ASR 引擎 | **m3**（zh→FunASR, en→whisperx） |
| 决定 SRT 是否要 AI 润色 | **m3**（看 cue 数 / 时长分布） |
| 决定 voice / rate / sample | **m3**（用户偏好） |
| 决定 segments 切点 | **m3**（看 SRT 语义段） |
| 标点重切 | **Python**（确定性算法） |
| 烧字幕 | **Python**（ffmpeg 调用） |
| 静音对齐 | **Python**（时长计算） |
| 抽帧 | **Python**（ffmpeg 1 行） |

**原则**：m3 做"判断"，Python 做"机械执行"。

---

## 📁 目录约定

```
D:\PIproject\skills\                   # 开发主目录
├── README.md                          # 总览
├── NOTES.md                           # 本文件
├── sync-to-pi.bat                     # 一键同步到 pi
├── aping-common/                      # 共享库
├── aping-transcribing-audio/
├── aping-regrouping-srt/
├── aping-burning-subtitles/
├── aping-dubbing-video/
└── aping-segmenting-video/

C:\Users\shuis\.pi\agent\skills\       # pi 加载（用 sync-to-pi.bat 同步）
├── aping-*                            # 5 个 skill 复制
└── aping-common/
```

---

## 🔮 未来工作

### 短期（可做）
- [ ] 把 `--verbose` 全程接入（log 替 print）
- [ ] aping-segmenting 用 m3 自动选切点（看 SRT 语义）
- [ ] aping-dubbing 加 `concat 段间静音填充`（让配音与原 SRT 边界对齐）
- [ ] GBK 修复应用到所有 5 个脚本（目前只改了 transcribe.py）

### 中期
- [ ] 评测 VoxCPM 克隆特定人声（需要找一段参考音频）
- [ ] 集成 wav2vec2 强制对齐（如果 FunASR 标点错误回退到 word-level）
- [ ] 加 `--no-burn-srt` 选项（让 SRT 与视频分离）
- [ ] 加 `make-cover` skill（视频封面自动生成）

### 长期
- [ ] 支持多机位（虽然您不要，先留接口）
- [ ] 集成 pyannote-audio 做 speaker diarization（多人对话）
- [ ] WebUI（让 m3 之外的工具能直接调用）

---

## 📊 性能数据（test.mp4 26.77s 720×1280）

| 阶段 | 时间 | 模型 |
|------|------|------|
| FunASR 转录 | 3.7s | paraformer-zh + VAD + 标点 |
| mmx 润色 SRT | ~5s | m3 (3 cue) |
| SRT 切片 | 2.2s | ffmpeg 重编码 |
| 抽帧 | 0.3s | ffmpeg |
| 烧字幕 | 4.5s | ffmpeg libass |
| edge-tts 配音 | 2.1s | 小晓中文 |
| **总时长** | **~18s** | - |
