---
name: aping-segmenting-video
description: 把长视频（讲座/播客/访谈）按话题切成 3-6 条独立短视频。**话题边界由 m3 读 SRT 决定**（不是算法自动），保证每段独立成立、有钩子有结论、不切到句子中间。切割采用**重编码模式**（不是流复制），避免字幕比声音早 0.6-1.5s。触发词："切成几段"、"分主题"、"拆成短视频"、"split into clips"。
---

# aping-segmenting-video

长视频 + SRT → 3-6 条独立短视频。

## 核心原则

1. **话题边界由 m3 判断**——不是 NLP/聚类/沉默检测（那些做不好"独立成立"这个标准）
2. **重编码切割**（`--reencode`）——流复制会让字幕比声音早 0.6-1.5s
3. **每段 30-90 秒**——抖音/视频号最佳时长

## 决策标准（让 m3 评估每段是否合格）

- ✅ **独立成立**——冷启动观众没看过原视频也能看懂
- ✅ **单一线索**——一个中心问题/洞见；中途换话题就该分两段
- ✅ **长度合适**——30-90s（视频号/抖音）
- ✅ **钩子 + 结论**——开头有主张/问题/画面，结尾有结论；不切到半句话
- ✅ **3-6 段最佳**——10 分钟视频切 4 段是常态；平淡中间段大胆删

## 使用方式

```bash
# 1. 让 m3 读 SRT 决定 segments.json（手动命令）
#    把 SRT 文本发给 m3，问：切成 4 段，给我 JSON

# 2. 切割（重编码模式，clip 精确在请求时间点开始）
python scripts/segment.py video.mp4 \
    --segments segments.json \
    --out output/ \
    --reencode
```

## segments.json 格式

```json
{
  "source_video": "input.mp4",
  "source_srt": "input.zh.srt",
  "segments": [
    {
      "id": 1,
      "slug": "ai-not-code",
      "title": "AI 时代不是写代码",
      "start": "00:01:23.460",
      "end": "00:02:35.220",
      "summary": "一句话说清这段的中心观点"
    }
  ]
}
```

## 输出

```
output/
├── clip_01_ai-not-code.mp4     # 切割好的视频（精确到帧）
├── clip_01_ai-not-code.srt     # 该段的 SRT（时间戳归零）
├── frame_01_ai-not-code.jpg    # 中点帧（封面参考）
└── segments.json               # 原始元数据
```

## 下一步

把 `clip_NN_*.mp4 + .srt` 丢给 `aping-burning-subtitles` 烧字幕。
