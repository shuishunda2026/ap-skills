"""
aping-segmenting-video: 长视频 + SRT → 多条独立短视频

切割采用重编码模式（--reencode）保证精确起始。
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "aping-common"))

from aping_common import (
    get_ffmpeg,
    get_ffprobe,
    ensure_dir,
    srt_time_to_seconds,
    seconds_to_srt_time,
    parse_srt,
    write_srt,
    safe_filename,
)


# =============================================================================
# segments.json 处理
# =============================================================================

def load_segments(segments_path: str) -> list:
    """加载 segments.json，统一时间戳为秒数"""
    with open(segments_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for seg in data["segments"]:
        seg["start_sec"] = srt_time_to_seconds(seg["start"])
        seg["end_sec"] = srt_time_to_seconds(seg["end"])
    return data["segments"]


# =============================================================================
# 视频切割
# =============================================================================

def cut_clip_reencode(video_path: str, start: float, end: float,
                      output_path: str):
    """
    重编码模式切割 - 精确到帧
    关键：-ss 在 -i 之前 = 快速 seek + 精确解码
    """
    duration = end - start
    cmd = [
        get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-i", video_path,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def extract_midpoint_frame(video_path: str, output_jpg: str):
    """提取视频中点帧作为封面参考"""
    # 先测时长
    cmd_probe = [
        get_ffprobe(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path,
    ]
    result = subprocess.run(cmd_probe, capture_output=True, text=True)
    # Windows 上 ffprobe 退出码可能异常，改为检查 stdout
    if not result.stdout.strip():
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    duration = float(result.stdout.strip())
    mid = duration / 2

    cmd = [
        get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{mid:.2f}",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "3",
        "-update", "1",  # 重要：只写一张图
        output_jpg
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not Path(output_jpg).exists():
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")


# =============================================================================
# SRT 切片
# =============================================================================

def slice_srt_for_clip(srt_path: str, start_sec: float, end_sec: float,
                       output_srt: str):
    """
    把主 SRT 中 [start_sec, end_sec] 区间的 cues 切出来，
    时间戳归零（即第一个 cue 从 0 开始）。
    """
    cues = parse_srt(srt_path)
    # 保留与区间有重叠的 cue
    sliced = []
    for cue in cues:
        if cue["end"] <= start_sec or cue["start"] >= end_sec:
            continue
        # 裁剪到区间
        new_start = max(cue["start"], start_sec) - start_sec
        new_end = min(cue["end"], end_sec) - start_sec
        sliced.append({
            "start": new_start,
            "end": new_end,
            "text": cue["text"],
        })

    write_srt(sliced, output_srt)
    return len(sliced)


# =============================================================================
# 主流程
# =============================================================================

def segment_video(video_path: str, segments_path: str,
                  output_dir: str, srt_path: str = None,
                  reencode: bool = True) -> list:
    """
    切割视频。
    返回生成的 clip 文件列表。
    """
    video_path = Path(video_path)
    segments = load_segments(segments_path)
    output_dir = Path(output_dir)
    ensure_dir(str(output_dir))

    if not reencode:
        print("WARNING: stream-copy mode may cause subtitle/audio sync issues."
              " Recommend --reencode (default).")

    generated = []
    for seg in segments:
        seg_id = seg["id"]
        slug = seg.get("slug", safe_filename(seg.get("title", f"seg{seg_id}")))
        title = seg.get("title", slug)
        start = seg["start_sec"]
        end = seg["end_sec"]
        duration = end - start

        base = f"clip_{seg_id:02d}_{slug}"
        clip_path = output_dir / f"{base}.mp4"
        frame_path = output_dir / f"frame_{seg_id:02d}_{slug}.jpg"

        print(f"[{seg_id}/{len(segments)}] {title}")
        print(f"  Range: {seg['start']} -> {seg['end']} ({duration:.1f}s)")

        # 切割
        cut_clip_reencode(str(video_path), start, end, str(clip_path))
        print(f"  [OK] Clip: {clip_path.name}")

        # 抽帧
        extract_midpoint_frame(str(clip_path), str(frame_path))
        print(f"  [OK] Frame: {frame_path.name}")

        # 切片 SRT
        if srt_path:
            srt_out = output_dir / f"{base}.srt"
            n = slice_srt_for_clip(srt_path, start, end, str(srt_out))
            print(f"  [OK] SRT ({n} cues): {srt_out.name}")

        generated.append({
            "clip": str(clip_path),
            "frame": str(frame_path),
            "srt": str(output_dir / f"{base}.srt") if srt_path else None,
            "title": title,
            "start": start,
            "end": end,
        })

    print(f"\n[OK] Generated {len(generated)} clips in {output_dir}")
    return generated


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="aping-segmenting-video: 长视频 → 多个独立短片"
    )
    parser.add_argument("video", help="输入长视频路径")
    parser.add_argument("--segments", required=True,
                        help="segments.json 路径（m3 生成的）")
    parser.add_argument("--srt", default=None,
                        help="源 SRT 路径（用于切片）")
    parser.add_argument("--out", default="./output", help="输出目录")
    parser.add_argument("--reencode", action="store_true", default=True,
                        help="重编码切割（默认开启，精确到帧）")
    parser.add_argument("--no-reencode", dest="reencode", action="store_false")
    args = parser.parse_args()

    segment_video(
        video_path=args.video,
        segments_path=args.segments,
        output_dir=args.out,
        srt_path=args.srt,
        reencode=args.reencode,
    )


if __name__ == "__main__":
    main()
