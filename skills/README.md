# PIproject 素材库

> 视频剪辑工作流的测试素材和 Skill 开发项目。
>
> **安装使用说明** 在 pi 加载后的 `~/.pi/agent/skills/ap-skills/README.md`（本仓库 README 不重复）。

## 📁 目录结构

```
D:\PIproject\
├── .gitignore              # 忽略 tmp/output/test.mp4 等
├── test.mp4                # 测试视频（手机竖拍，26.77s 720×1280）
├── skills/                 # 5 个 aping skill + 共享库
│   ├── README.md
│   ├── NOTES.md
│   ├── sync-to-pi.bat
│   ├── aping-transcribing-audio/
│   ├── aping-regrouping-srt/
│   ├── aping-burning-subtitles/
│   ├── aping-dubbing-video/
│   ├── aping-segmenting-video/
│   └── aping-common/
├── test_output/            # 测试产物（gitignored）
│   ├── test.funasr.srt
│   ├── test.funasr.polished.srt
│   ├── clips_funasr/       # 切片+烧字幕成片
│   └── test.dubbed.mp4
├── .dub_work/              # 配音中间产物（gitignored）
├── Quant/                  # 其他项目
├── ai-assistant-guide/
├── ai-assistant-speech/
├── childrens-day/
├── qiting-ai-presentation/
├── 云获客/
├── 如何正确使用AI助手.md
└── 老胡短视频内容营销陪跑营（第二期）开营说明.pdf
```

## 🎬 测试视频

**`test.mp4`**：26.77s 720×1280 HEVC+AAC，2.2MB，口播中文。

测试过的内容：
- ✅ 完整流水线（转录 → 重切 → 切片 → 烧字幕 → 配音）
- ✅ ASR 引擎：whisperx small vs FunASR paraformer-zh（FunASR 完胜）
- ✅ TTS 引擎：edge-tts / mmx / VoxCPM
- ✅ AI 润色：mmx M3 修正错别字

## 🔧 日常开发流

```bash
# 1. 改 skills/ 下的代码
# 2. 跑 sync-to-pi.bat 同步到 pi agent
cmd.exe //c "D:\\PIproject\\skills\\sync-to-pi.bat"

# 3. 提交到 GitHub
cd D:/PIproject
git add skills/
git commit -m "feat: 你的改动"
git push
```

## 🔗 相关链接

- GitHub: https://github.com/shuishunda2026/ap-skills
- pi skill 目录: `~/.pi/agent/skills/ap-skills/`
- 王建硕原版: https://github.com/jianshuo/claude-skills
