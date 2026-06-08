"""
aping-burning-subtitles: 视频 + SRT → 烧好字幕的成片

关键：一次 ffmpeg 编码完成所有操作。
"""

import argparse
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "aping-common"))

from aping_common import (
    get_ffmpeg,
    get_cjk_font,
    run_ffmpeg,
    get_duration,
    ensure_dir,
)


# =============================================================================
# 核心：构造 libass 字幕滤镜
# =============================================================================

def build_subtitle_filter(srt_path: str, font: str, fontsize: int,
                          font_color: str = "&H00FFFFFF",
                          outline_color: str = "&H00000000",
                          margin_v: int = 40,
                          margin_lr: int = 20,
                          border_style: int = 1,
                          outline: int = 2,
                          shadow: int = 1) -> str:
    """
    构造 libass subtitles 滤镜字符串
    注意 force_style 里的逗号要转义为 \,
    libass 路径转义：\ -> \\\\, ' -> \\\'
    """
    # libass 路径转义规则
    # \ -> \\, ' -> \'
    srt_escaped = str(srt_path)
    srt_escaped = srt_escaped.replace("\\", "\\\\")  # 路径反斜杠
    srt_escaped = srt_escaped.replace(":", "\\:")    # 盘符冒号
    srt_escaped = srt_escaped.replace("'", "\\'")    # 单引号

    style_parts = [
        f"FontName={font}",
        f"FontSize={fontsize}",
        f"PrimaryColour={font_color}",
        f"OutlineColour={outline_color}",
        f"BorderStyle={border_style}",
        f"Outline={outline}",
        f"Shadow={shadow}",
        f"MarginL={margin_lr}",
        f"MarginR={margin_lr}",
        f"MarginV={margin_v}",
        f"Alignment=2",  # 2 = 底部居中
    ]
    style_str = "\\,".join(style_parts)
    return f"subtitles='{srt_escaped}':force_style='{style_str}'"


# =============================================================================
# 主流程
# =============================================================================

def burn_subtitles(video_path: str, srt_path: str = None,
                   dub_path: str = None, output_path: str = None,
                   font: str = None, fontsize: int = 12,
                   bed_volume: float = 0.18,
                   preview: int = 0,
                   no_burn: bool = False) -> str:
    """
    烧字幕（+ 混配音）到视频，一次 ffmpeg 编码。

    preview: 0 = 全片, >0 = 只烧前 N 秒测试
    no_burn: True = 不烧字幕，只混音
    """
    if output_path is None:
        output_path = str(Path(video_path).with_name(
            Path(video_path).stem + ".burned.mp4"
        ))

    if font is None:
        try:
            font = get_cjk_font()
        except FileNotFoundError:
            print("WARNING: No CJK font found, falling back to 'Arial'")
            font = "Arial"

    # 构造输入参数
    inputs = ["-i", video_path]
    if dub_path:
        inputs += ["-i", dub_path]

    # 构造 filter_complex
    filters = []

    # 视频滤镜
    if srt_path and not no_burn:
        sub_filter = build_subtitle_filter(srt_path, font, fontsize)
        filters.append(f"[0:v]{sub_filter}[v]")
    else:
        filters.append("[0:v]copy[v]")

    # 音频滤镜
    if dub_path:
        # 有配音：原声降噪 + 配音全音量
        if srt_path and not no_burn:
            # filter_complex 中要避开 [v] 标签已用过
            filters.append(f"[0:a]volume={bed_volume}[orig]")
            filters.append(f"[1:a]volume=1.0[dub]")
            filters.append(f"[orig][dub]amix=inputs=2:duration=longest:normalize=0[a]")
        else:
            filters.append(f"[0:a]volume={bed_volume}[orig]")
            filters.append(f"[1:a]volume=1.0[dub]")
            filters.append(f"[orig][dub]amix=inputs=2:duration=longest:normalize=0[a]")
    else:
        # 没配音：原声直通
        if srt_path and not no_burn:
            filters.append(f"[0:a]acopy[a]")
        else:
            filters.append(f"[0:a]acopy[a]")

    filter_complex = ";\n".join(filters)

    # 构造最终命令
    cmd = [get_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    cmd += inputs
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", "[v]", "-map", "[a]"]

    if preview > 0:
        cmd += ["-t", str(preview)]

    # 视频编码参数
    if srt_path and not no_burn:
        # 烧字幕需要重编码
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-pix_fmt", "yuv420p"]
    else:
        # 不烧字幕可以流复制
        cmd += ["-c:v", "copy"]

    # 音频编码
    cmd += ["-c:a", "aac", "-b:a", "192k"]

    cmd += [output_path]

    print(f"FFmpeg command: {' '.join(cmd[:10])}...")
    print(f"Font: {font}, FontSize: {fontsize}")
    print(f"Mode: {'preview ' + str(preview) + 's' if preview else 'full'}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg stderr: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed with code {result.returncode}")

    print(f"[OK] Output: {output_path}")
    return output_path


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="aping-burning-subtitles: 烧字幕+混配音到视频"
    )
    parser.add_argument("video", help="输入视频路径")
    parser.add_argument("--srt", default=None, help="字幕 SRT 路径")
    parser.add_argument("--dub", default=None, help="配音视频/音频路径")
    parser.add_argument("--out", default=None, help="输出视频路径")
    parser.add_argument("--font", default=None, help="字体（默认 msyh 微软雅黑）")
    parser.add_argument("--fontsize", type=int, default=12, help="字号")
    parser.add_argument("--bed_volume", type=float, default=0.18,
                        help="原声背景音量（默认 0.18）")
    parser.add_argument("--preview", type=int, default=0,
                        help="只烧前 N 秒（调试用）")
    parser.add_argument("--no-burn", action="store_true",
                        help="不烧字幕，只混配音")
    args = parser.parse_args()

    if not args.srt and not args.dub:
        parser.error("Must provide --srt or --dub (or both)")

    burn_subtitles(
        video_path=args.video,
        srt_path=args.srt,
        dub_path=args.dub,
        output_path=args.out,
        font=args.font,
        fontsize=args.fontsize,
        bed_volume=args.bed_volume,
        preview=args.preview,
        no_burn=args.no_burn,
    )


if __name__ == "__main__":
    main()
