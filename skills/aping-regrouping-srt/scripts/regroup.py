"""
aping-regrouping-srt: SRT 标点重切 + AI 润色错别字
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "aping-common"))

from aping_common import parse_srt, write_srt


# =============================================================================
# 标点重切（不依赖 LLM）
# =============================================================================

HARD_PUNCT = set("。！？!?")
SOFT_PUNCT = set("，、；,;:")


def regroup_cues_by_punctuation(cues: list, max_chars: int = 18,
                                min_chars_for_soft: int = 8) -> list:
    """
    把整个 SRT 的文本串起来，按标点重切，再重新分配时间。
    注：会改变 cue 数量和边界，不修改文本。
    """
    if not cues:
        return cues

    # 把所有 cue 文本和词级时间戳拼起来
    # 注：原 cue 不一定是 word-level，我们用 cue 级别处理
    full_text = ""
    boundary_points = []  # (char_index_in_full, time)

    for cue in cues:
        full_text += cue["text"]
        boundary_points.append((len(full_text), cue["end"]))

    # 按标点切
    new_cues = []
    buf_text = ""
    buf_start_time = cues[0]["start"]

    for i, ch in enumerate(full_text):
        buf_text += ch
        # 找最接近的边界点的时间戳
        cur_time = boundary_points[0][1] if not boundary_points else 0
        for bp_idx, (bp_pos, bp_time) in enumerate(boundary_points):
            if i + 1 <= bp_pos:
                cur_time = bp_time
                break

        last_ch = buf_text[-1]
        should_flush = False
        if last_ch in HARD_PUNCT:
            should_flush = True
        elif last_ch in SOFT_PUNCT and len(buf_text) >= min_chars_for_soft:
            should_flush = True
        elif len(buf_text) >= max_chars:
            should_flush = True

        if should_flush:
            new_cues.append({
                "start": buf_start_time,
                "end": cur_time,
                "text": buf_text.strip(),
            })
            buf_text = ""
            # 下一个 cue 从当前时间开始
            buf_start_time = cur_time

    if buf_text.strip():
        new_cues.append({
            "start": buf_start_time,
            "end": cues[-1]["end"],
            "text": buf_text.strip(),
        })

    return new_cues


# =============================================================================
# AI 智能重切（需要 mmx CLI）—— 解决无标点长 cue 问题
# =============================================================================

def ai_resegment(srt_path: str, output_path: str) -> str:
    """
    让 m3 重切 SRT。

    策略：把 SRT 发送给 m3，要求：
    1. 读完上下文后，在自然的语义停顿处切（每段 1-4 句）
    2. 输出严格的 JSON：{segments: [{start, end, text}, ...]}
    3. text 必须是原文本的连续子串（不能重写、改字、合并 cue）
    4. start/end 必须从原 cue 列表里选（不能编造）
    """
    cues = parse_srt(srt_path)
    if not cues:
        return srt_path

    # 准备给 m3 的输入
    cue_summary = []
    full_text = ""
    for i, c in enumerate(cues):
        # 把全文本索引映射回去
        seg_text = c["text"]
        start_idx = len(full_text)
        full_text += seg_text
        end_idx = len(full_text)
        cue_summary.append({
            "i": i + 1,
            "start": round(c["start"], 3),
            "end": round(c["end"], 3),
            "char_range": [start_idx, end_idx],
        })

    system = "你是一个中文口播字幕重切助手。任务: 读口播 SRT 字幕,在自然语义停顿处重切为多个短 cue。输入: 1-4 个长 cue 口播。输出: 重切后的 cue 列表,每段 1-4 个完整短句,3-5 秒,≤ 18 个中文字符。硬规则: (1) 严格 JSON {\"segments\":[{\"start\":<秒>,\"end\":<秒>,\"text\":\"<原文>\"}]} (2) text 必须是原 SRT 文本的连续子串,不允许重写/改字/重复字 (3) start/end 必须等于某个原 cue 的 start/end (4) 多段拼起来必须 100% 覆盖原文本 (5) 不在原文本里出现的字一律不准出现 (6) 只输出 JSON,不要任何解释。"

    user = f"""原 SRT 文本:
{full_text}

原 cue 列表:
{json.dumps(cue_summary, ensure_ascii=False, indent=2)}

请输出重切后的 JSON:"""

    import subprocess
    import shutil
    import tempfile
    import os
    print("Calling mmx to AI-resegment...")
    mmx_cmd = shutil.which("mmx.cmd") or shutil.which("mmx")
    if not mmx_cmd:
        print("ERROR: mmx not found in PATH", file=sys.stderr)
        return srt_path
    # 用 messages-file 避免 Windows subprocess 处理多行问题
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    msg_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(messages, msg_file, ensure_ascii=False)
    msg_file.close()
    try:
        result = subprocess.run(
            [mmx_cmd, "text", "chat",
             "--messages-file", msg_file.name,
             "--output", "text",
             "--max-tokens", "4096"],
            capture_output=True, text=True, encoding="utf-8"
        )
    finally:
        os.unlink(msg_file.name)
    if result.returncode != 0:
        print(f"mmx failed: {result.stderr}", file=sys.stderr)
        return srt_path

    raw = result.stdout.strip()
    # 提取 JSON (有时 mmx 会在外面包 ```json ... ```)
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        print("No JSON found in mmx output:")
        print(raw)
        return srt_path

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        print(f"JSON parse failed: {e}")
        print(raw[:500])
        return srt_path

    new_cues = data.get("segments", [])
    if not new_cues:
        print("mmx returned empty segments list")
        return srt_path

    # 验证 1: 拼起来 == 原文
    reconstructed = "".join(s["text"] for s in new_cues)
    # 去除空白后比较
    orig_clean = re.sub(r"\s+", "", full_text)
    recon_clean = re.sub(r"\s+", "", reconstructed)
    if orig_clean != recon_clean:
        print(f"WARNING: reconstructed text differs from original.")
        print(f"  Original  : {orig_clean[:80]!r}...")
        print(f"  Reconstructed: {recon_clean[:80]!r}...")
        # 如果差异 ≤ 2 个字 仍接受 (AI 可能加了标点)
        # 精确 100% 匹配 才算成功
        if orig_clean != recon_clean:
            print("  Falling back to original SRT.")
            return srt_path

    # 验证 2: start/end 都在原 cue 中
    valid_starts = {c["start"] for c in cues}
    valid_ends = {c["end"] for c in cues}
    for s in new_cues:
        if s["start"] not in valid_starts or s["end"] not in valid_ends:
            print(f"  WARNING: AI used non-cue boundary: {s}")
            return srt_path

    write_srt(new_cues, output_path)
    print(f"[OK] AI-resegmented {len(cues)} cues -> {len(new_cues)} cues")
    print(f"      Saved to: {output_path}")
    return output_path


# =============================================================================
# AI 润色（需要 mmx CLI）
# =============================================================================

def polish_with_mmx(srt_path: str, output_path: str) -> str:
    """
    用 mmx（MiniMax）润色错别字。
    修正规则：只改明显的同音错别字，不动时间戳，不动专有名词。
    """
    cues = parse_srt(srt_path)

    # 准备发给 LLM 的内容
    srt_text = "\n".join(
        f"[{i+1}] {c['text']}"
        for i, c in enumerate(cues)
    )

    prompt = f"""你是一个字幕错别字修正助手。下面是视频字幕。
    请**只**修正明显的同音错别字（如"意数"→"总数"、"虚求"→"需求"），
    这些修正必须能从上下文 100% 确定。

    **硬规则**：
    1. **不要**改时间戳、不要改 cue 数量、不要改 cue 边界
    2. **不要**改人名、品牌、产品名、公司名
    3. **不要**润色语序、不要删字、不要加字、不要改语气
    4. 数字、量词保留原样（"50万" 不要变 "500,000"）
    5. 不确定的字**保留原样**并在末尾用 (存疑:xxx) 标出

    输出格式：保持 `[1] 文本` 一行一条的格式，**只输出修正后的内容**，不要解释。
    如果没有需要修正的，原样输出。

    待修正字幕：
    {srt_text}
    """

    print("Calling mmx to polish SRT...")
    import subprocess
    import shutil
    import tempfile
    import os
    mmx_cmd = shutil.which("mmx.cmd") or shutil.which("mmx")
    if not mmx_cmd:
        print("ERROR: mmx not found in PATH", file=sys.stderr)
        return srt_path
    system = "你是字幕错别字修正助手。只修正明显同音错别字,不动时间戳/cue边界/人名/数字/量词。不润色语序、不删字。输出 [1] 文本 一行一条,不要解释。"
    user = f"请修正下面的 SRT(保持 [n] 格式,时间戳别管,只输出修正后内容):\n\n{srt_text}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    msg_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(messages, msg_file, ensure_ascii=False)
    msg_file.close()
    try:
        result = subprocess.run(
            [mmx_cmd, "text", "chat",
             "--messages-file", msg_file.name,
             "--output", "text"],
            capture_output=True, text=True, encoding="utf-8"
        )
    finally:
        os.unlink(msg_file.name)
    if result.returncode != 0:
        print(f"mmx failed: {result.stderr}", file=sys.stderr)
        print("Falling back to original SRT (no polish).")
        return srt_path

    output_text = result.stdout.strip()
    # 解析 [n] 文本 格式
    new_cues = []
    for line in output_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = None
        import re
        m = re.match(r"^\[(\d+)\]\s*(.*)$", line)
        if m:
            idx = int(m.group(1))
            text = m.group(2)
            if 0 <= idx - 1 < len(cues):
                new_cue = dict(cues[idx - 1])
                new_cue["text"] = text
                new_cues.append(new_cue)

    if len(new_cues) != len(cues):
        print(f"WARNING: mmx returned {len(new_cues)} cues, original has {len(cues)}."
              " Falling back to original.")
        return srt_path

    write_srt(new_cues, output_path)
    print(f"[OK] Polished SRT saved to: {output_path}")

    # 输出 diff
    diff_count = sum(1 for o, n in zip(cues, new_cues) if o["text"] != n["text"])
    print(f"      Modified {diff_count}/{len(cues)} cues")
    return output_path


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="aping-regrouping-srt: SRT 重切 + AI 润色"
    )
    parser.add_argument("input", help="输入 SRT 路径")
    parser.add_argument("--mode", choices=["polish", "regroup", "ai"],
                        default="polish",
                        help="模式：polish=AI 润色错别字（不动时间戳），"
                             "regroup=按标点重切, "
                             "ai=AI 智能重切（解决无标点长 cue）")
    parser.add_argument("--max_chars", type=int, default=18)
    parser.add_argument("--output", "-o", default=None,
                        help="输出 SRT 路径（默认 input.regrouped.srt）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    if args.output is None:
        if args.mode == "polish":
            suffix = ".polished.srt"
        elif args.mode == "ai":
            suffix = ".ai.srt"
        else:
            suffix = ".regrouped.srt"
        output_path = input_path.with_suffix("").with_suffix(suffix)
    else:
        output_path = Path(args.output)

    if args.mode == "polish":
        polish_with_mmx(str(input_path), str(output_path))
    elif args.mode == "ai":
        ai_resegment(str(input_path), str(output_path))
    else:  # regroup
        cues = parse_srt(str(input_path))
        new_cues = regroup_cues_by_punctuation(cues, max_chars=args.max_chars)
        write_srt(new_cues, str(output_path))
        print(f"[OK] Regrouped {len(cues)} cues → {len(new_cues)} cues")
        print(f"      Saved to: {output_path}")


if __name__ == "__main__":
    main()
