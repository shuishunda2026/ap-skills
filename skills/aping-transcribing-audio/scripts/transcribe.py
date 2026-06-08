"""
aping-transcribing-audio: 视频/音频 → SRT 字幕

调用 whisperx（OpenAI Whisper + wav2vec2 词级对齐），
输出按标点切分干净的 SRT 文件。
"""

import argparse
import sys
import re
from pathlib import Path

# 把 aping-common 加到 path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "aping-common"))

from aping_common import (
    DEFAULT_OUTPUT_DIR,
    ensure_dir,
    seconds_to_srt_time,
    setup_console,
    log,
)


# =============================================================================
# 标点重切
# =============================================================================

# 强切标点：遇到就 flush
HARD_PUNCT = set("。！？!?")
# 软切标点：达到 MIN_CHARS 才 flush
SOFT_PUNCT = set("，、；,;:")


def regroup_by_punctuation(words: list, max_chars: int = 18,
                          min_chars_for_soft: int = 8) -> list:
    """
    把词级时间戳结果按标点重切为 cue 列表。

    words: [{"word": "...", "start": 0.1, "end": 0.5}, ...]
    返回: [{"start": 0.1, "end": 3.5, "text": "..."}, ...]

    参考王建硕 3 步法：
    - TARGET_DUR/MAX_CUE_DUR 硬限
    - MAX_GAP 沉默阈值
    - 超 MAX_CHARS 递归用 word-level gaps 切
    - 内部标点切用 proportional 时间戳
    """
    if not words:
        return []

    # 常量（参考王建硕默认值）
    TARGET_DUR = 3.0
    MAX_CUE_DUR = 5.0
    MAX_GAP = 1.0

    # Step 1: 先按 word 拼成 "phrases"（以强标点切开的句级）
    #         phrases 之间天然是停顿点
    phrases = []
    cur_text = ""
    cur_start = None
    cur_end = None

    def flush_phrase():
        nonlocal cur_text, cur_start, cur_end
        if cur_text.strip() and cur_start is not None:
            phrases.append({
                "start": cur_start,
                "end": cur_end,
                "text": cur_text.strip(),
            })
        cur_text = ""
        cur_start = None
        cur_end = None

    for w in words:
        word = w["word"]
        if cur_start is None:
            cur_start = w["start"]
        cur_text += word
        cur_end = w["end"]
        last_char = word[-1] if word else ""

        # 强标点 → 立即切
        if last_char in HARD_PUNCT:
            flush_phrase()
        # 软标点 + 够长 → 切
        elif last_char in SOFT_PUNCT and len(cur_text) >= min_chars_for_soft:
            flush_phrase()
        # 【关键】无标点时,超 max_chars → 硬切(以免一句话被堆成 20+ 字长 phrase)
        elif len(cur_text) >= max_chars:
            flush_phrase()

    flush_phrase()

    if not phrases:
        return []

    # Step 2: 把 phrase 拼成 cue（按 TARGET_DUR / MAX_CUE_DUR / MAX_GAP）
    cues = []
    buf_phrases = []
    buf_start = None
    buf_end = None
    buf_text = ""

    def flush_cue():
        nonlocal buf_phrases, buf_start, buf_end, buf_text
        if buf_text.strip() and buf_start is not None:
            cues.append({
                "start": buf_start,
                "end": buf_end,
                "text": buf_text.strip(),
            })
        buf_phrases = []
        buf_start = None
        buf_end = None
        buf_text = ""

    for p in phrases:
        # 检查 word 间 gap（看 word 列表中前一个 phrase 的末 word 之后，
        # 与下一个 phrase 首 word 之前的 gap）
        prev_end = buf_end if buf_end is not None else p["start"]
        gap = p["start"] - prev_end

        # 触发 flush 条件（任一）：
        # 1. 沉默 ≥ MAX_GAP → 强制断
        # 2. 累计时长 ≥ TARGET_DUR 且新 phrase 带入新内容
        # 3. 累计时长 > MAX_CUE_DUR → 硬限
        # 4. 字符超 max_chars → 硬限
        will_dur = (p["end"] - buf_start) if buf_start is not None else 0
        # 累计字符数
        will_chars = len(buf_text) + len(p["text"])
        if buf_start is not None and (
            gap >= MAX_GAP
            or (buf_end - buf_start) >= TARGET_DUR  # 到达目标时长 → 断
            or will_dur > MAX_CUE_DUR                # 超硬限
            or will_chars > max_chars                 # 超字符限
        ):
            flush_cue()

        if buf_start is None:
            buf_start = p["start"]
        buf_end = p["end"]
        buf_text += p["text"]

    flush_cue()

    # Step 3: 逐 cue 检查是否超 MAX_CHARS 或 MAX_CUE_DUR
    #         超了则按字符位置 proportional 切
    final = []
    for c in cues:
        c_dur = c["end"] - c["start"]
        if len(c["text"]) <= max_chars and c_dur <= MAX_CUE_DUR:
            final.append(c)
            continue

        # 需要切：按 max_chars 划块，proportional 时间戳
        text = c["text"]
        n = (len(text) + max_chars - 1) // max_chars
        chunk_size = len(text) / n
        for i in range(n):
            chunk_text = text[int(i * chunk_size): int((i + 1) * chunk_size)]
            t_start = c["start"] + (i * c_dur / n)
            t_end = c["start"] + ((i + 1) * c_dur / n)
            final.append({
                "start": t_start,
                "end": t_end,
                "text": chunk_text.strip(),
            })
    return final


# =============================================================================
# FunASR 后端（中文专用，自动标点）
# =============================================================================

def transcribe_with_funasr(input_path: str, max_chars: int = 18) -> list:
    """
    用 FunASR 转录 → SRT cue 列表。

    FunASR 返回 {"text": "全文带标点", "timestamp": [[s_ms,e_ms], ...]}
    - timestamp 与 text 中**非标点字**逐个对应
    - 按硬切（。！？）+ 软切（，；）+ max_chars 三档制控
    """
    from funasr import AutoModel

    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    print("[1/2] Loading FunASR...")
    model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad",
                      punc_model="ct-punc", device="cpu")

    print("[2/2] Transcribing...")
    result = model.generate(input=str(input_path))
    text = result[0].get("text", "")
    ts = result[0].get("timestamp", [])
    if not text or not ts:
        return []

    PUNCT = set("，。！？!?、；,;:. ")
    HARD = set("。！？!?")
    SOFT = set("，、；,;:")

    # 过滤标点(保留非标点字 → ts 一一对应)
    non_punct_idx = [i for i, c in enumerate(text) if c not in PUNCT]
    if len(non_punct_idx) != len(ts):
        n = min(len(non_punct_idx), len(ts))
        non_punct_idx, ts = non_punct_idx[:n], ts[:n]

    # 按 text 顺序扫描, 决定切点
    out = []
    chunk_start = 0
    for i, ch in enumerate(text):
        # 这个 chunk 够长? ch 是软标点? 触发软切
        seg_text = text[chunk_start:i + 1]
        non_punct_in_seg = sum(1 for c in seg_text if c not in PUNCT)
        should_soft_cut = (
            ch in SOFT
            and non_punct_in_seg >= max_chars
        )
        should_hard_cut = ch in HARD
        if should_soft_cut or should_hard_cut:
            seg = seg_text.strip()
            if seg:
                start_ms, end_ms = _segment_time(text, ts, non_punct_idx,
                                                  chunk_start, i + 1)
                out.append({
                    "start": start_ms / 1000.0,
                    "end": end_ms / 1000.0,
                    "text": seg,
                })
            chunk_start = i + 1

    # 收尾
    if chunk_start < len(text):
        seg = text[chunk_start:].strip()
        if seg:
            start_ms, end_ms = _segment_time(text, ts, non_punct_idx,
                                              chunk_start, len(text))
            out.append({
                "start": start_ms / 1000.0,
                "end": end_ms / 1000.0,
                "text": seg,
            })
    return out


def _segment_time(text, ts, non_punct_idx, seg_text_start, seg_text_end):
    """
    seg_text 区间 → (start_ms, end_ms)。
    按 seg 内**第一个/最后一个非标点字**的 ts 定位。
    """
    n = len(non_punct_idx)
    if n == 0:
        return 0, 0
    # first: 最小 j 使 ci >= seg_text_start
    first_ts_i = 0
    for j, ci in enumerate(non_punct_idx):
        if ci >= seg_text_start:
            first_ts_i = j
            break
    # last: 最大 j 使 ci < seg_text_end
    last_ts_i = n - 1
    for j in range(n - 1, -1, -1):
        if non_punct_idx[j] < seg_text_end:
            last_ts_i = j
            break
    return ts[first_ts_i][0], ts[last_ts_i][1]


def detect_engine(language: str, explicit: str = None) -> str:
    """根据语言/显式参数选引擎"""
    if explicit:
        return explicit
    if language.startswith("zh"):
        return "funasr"
    return "whisperx"


# =============================================================================
# 主流程
# =============================================================================

def transcribe(input_path: str, language: str = "zh", model_name: str = "small",
               device: str = "cpu", compute_type: str = "int8",
               batch_size: int = 8, max_chars: int = 18,
               output_path: str = None,
               engine: str = "auto") -> str:
    """
    转录音/视频，返回输出 SRT 路径。
    engine: auto / funasr / whisperx
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    # 输出路径
    if output_path:
        output_srt = Path(output_path)
    else:
        output_srt = input_path.with_suffix(".srt")

    actual_engine = detect_engine(language, explicit=engine)
    print(f"Engine: {actual_engine} (lang={language})")

    if actual_engine == "funasr":
        cues = transcribe_with_funasr(
            input_path=str(input_path),
            max_chars=max_chars,
        )
    else:  # whisperx
        import whisperx  # 延迟导入

        print(f"[1/3] Loading model {model_name} on {device} ({compute_type})...")
        model = whisperx.load_model(model_name, device=device, compute_type=compute_type)

        print(f"[2/3] Loading audio & transcribing...")
        audio = whisperx.load_audio(str(input_path))
        result = model.transcribe(audio, batch_size=batch_size, language=language)
        detected_lang = result.get("language", language)
        print(f"      Detected language: {detected_lang}")

        # 词级对齐
        print(f"[3/3] Aligning words...")
        align_model, metadata = whisperx.load_align_model(
            language_code=detected_lang, device=device
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device=device
        )

        # 收集所有 words（whisperx 对齐后会带 word-level 时间戳）
        all_words = []
        for seg in result["segments"]:
            seg_words = seg.get("words", [])
            for w in seg_words:
                if w.get("start") is None or w.get("end") is None:
                    continue
                all_words.append({
                    "word": w["word"],
                    "start": float(w["start"]),
                    "end": float(w["end"]),
                })

        if not all_words:
            print("WARNING: No word-level timestamps found. Output may be empty.")
            return str(output_srt)

        # 标点重切
        cues = regroup_by_punctuation(all_words, max_chars=max_chars)

    print(f"      Generated {len(cues)} cues")

    # 写 SRT
    from aping_common import write_srt
    write_srt(cues, str(output_srt))
    print(f"[OK] Saved to: {output_srt}")
    return str(output_srt)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="aping-transcribing-audio: 音视频 → SRT 字幕"
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="打印详细日志")
    parser.add_argument("input", help="输入视频或音频路径")
    parser.add_argument("--language", "-l", default="zh",
                        help="源语言代码（zh/en/ja/...），必传，默认 zh")
    parser.add_argument("--model", "-m", default="small",
                        choices=["tiny", "base", "small", "medium",
                                 "large-v2", "large-v3", "large-v3-turbo"],
                        help="Whisper 模型大小")
    parser.add_argument("--device", "-d", default="cpu",
                        choices=["cpu", "cuda"],
                        help="推理设备")
    parser.add_argument("--compute_type", default="int8",
                        help="量化类型：int8/float16/float32")
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--max_chars", type=int, default=18,
                        help="单条字幕最大字符数（中文 18，英文 42）")
    parser.add_argument("--output", "-o", default=None,
                        help="输出 SRT 路径（默认与输入同名）")
    parser.add_argument("--engine", default="auto",
                        choices=["auto", "funasr", "whisperx"],
                        help="ASR 引擎: auto=中文 funasr / 其他 whisperx")
    args = parser.parse_args()
    setup_console(verbose=args.verbose)

    srt_path = transcribe(
        input_path=args.input,
        language=args.language,
        model_name=args.model,
        device=args.device,
        compute_type=args.compute_type,
        batch_size=args.batch_size,
        max_chars=args.max_chars,
        output_path=args.output,
        engine=args.engine,
    )
    print(f"\nNext step: aping-regrouping-srt (标点重切+润色) → aping-burning-subtitles (烧字幕)")


if __name__ == "__main__":
    main()
