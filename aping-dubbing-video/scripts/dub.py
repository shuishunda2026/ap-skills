"""
aping-dubbing-video: 视频 + SRT → 配音视频

引擎路由：
- edge-tts: zh-CN-* / en-*-Neural
- VoxCPM: zh_*_bigtts
- mmx: 其他
"""

import argparse
import asyncio
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "aping-common"))

from aping_common import (
    parse_srt,
    write_srt,
    get_ffmpeg,
    get_ffprobe,
    ensure_dir,
)


# =============================================================================
# 引擎路由
# =============================================================================

def detect_engine(voice_id: str) -> str:
    """根据 voice ID 判断引擎"""
    if "_bigtts" in voice_id:
        return "voxcpm"
    if voice_id.startswith("mmx:"):
        return "mmx"
    return "edge-tts"


# =============================================================================
# edge-tts 合成（单进程批量，避免限流）
# =============================================================================

async def edge_tts_synthesize(text: str, voice: str, output_mp3: str,
                               rate: str = "+0%", pitch: str = "+0Hz"):
    """用 edge-tts 合成单条"""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_mp3)


async def edge_tts_batch(texts_and_voices: list, output_dir: str,
                         rate: str = "+0%", pitch: str = "+0Hz"):
    """
    批量合成 edge-tts，单进程内顺序执行。
    texts_and_voices: [(text, voice, output_mp3), ...]
    """
    for text, voice, out in texts_and_voices:
        await edge_tts_synthesize(text, voice, out, rate, pitch)


# =============================================================================
# VoxCPM 合成
# =============================================================================

def voxcpm_synthesize(text: str, voice: str, output_mp3: str,
                      reference_audio: str = None, reference_text: str = None,
                      emotion: str = "calm", emotion_scale: int = 4):
    """用 VoxCPM CLI 合成单条"""
    cmd = [
        "voxcpm", "design",
        "--text", text,
        "--output", output_mp3,
        "--model-path", voice,
    ]
    if emotion:
        cmd += ["--control", emotion]
    if reference_audio:
        cmd += ["--reference-audio", reference_audio]
    subprocess.run(cmd, check=True, capture_output=True)


# =============================================================================
# mmx 合成
# =============================================================================

def mmx_synthesize(text: str, voice: str, output_mp3: str):
    """用 mmx CLI 合成单条"""
    import shutil
    voice_id = voice.replace("mmx:", "")
    mmx_cmd = shutil.which("mmx.cmd") or shutil.which("mmx")
    if not mmx_cmd:
        raise FileNotFoundError("mmx CLI not found in PATH")
    cmd = [mmx_cmd, "speech", "synthesize",
           "--text", text,
           "--voice", voice_id,
           "--out", output_mp3,
           "--format", "mp3"]
    subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")


# =============================================================================
# 时长对齐
# =============================================================================

def get_audio_duration(path: str) -> float:
    """用 ffprobe 测音频时长"""
    result = subprocess.run(
        [get_ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True
    )
    return float(result.stdout.strip())


def atempo_chain(factor: float) -> str:
    """构造 atempo 滤镜链（atempo 单次限制 0.5-2.0）"""
    if 0.5 <= factor <= 2.0:
        return f"atempo={factor:.4f}"
    # 多级链
    parts = []
    remaining = factor
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining *= 2
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def align_to_target(input_mp3: str, output_mp3: str, target_dur: float):
    """
    把音频对齐到目标时长。
    - 太长：atempo 加速（最低 0.82x）
    - 太短：补静音（不拉伸 - 拉伸会变声）
    """
    actual_dur = get_audio_duration(input_mp3)
    if abs(actual_dur - target_dur) < 0.1:
        # 已经在误差范围内
        shutil.copy(input_mp3, output_mp3)
        return

    if actual_dur > target_dur:
        # 需要加速（不能低于 0.82）
        factor = max(0.82, target_dur / actual_dur)
        af = atempo_chain(factor)
        cmd = [
            get_ffmpeg(), "-y", "-i", input_mp3,
            "-af", af,
            output_mp3
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        new_dur = get_audio_duration(output_mp3)
    else:
        # 太短：直接补静音
        shutil.copy(input_mp3, output_mp3)
        new_dur = actual_dur

    # 如果还短，补静音(用 wav 统一采样率/声道)
    if new_dur < target_dur - 0.1:
        silence_dur = target_dur - new_dur
        tmp = output_mp3 + ".tmp.wav"
        # 先生成 wav (采样率匹配原音频)
        probe = subprocess.run([
            get_ffprobe(), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels",
            "-of", "csv=p=0", output_mp3
        ], capture_output=True, text=True, check=True)
        sr_ch = probe.stdout.strip().split(",")
        sr = sr_ch[0] if len(sr_ch) > 0 and sr_ch[0] else "24000"
        ch = sr_ch[1] if len(sr_ch) > 1 and sr_ch[1] else "1"
        # 1. 生成静音 wav
        silence_wav = output_mp3 + ".silence.wav"
        cmd = [
            get_ffmpeg(), "-y", "-f", "lavfi",
            "-i", f"anullsrc=channel_layout={'mono' if ch=='1' else 'stereo'}:sample_rate={sr}",
            "-t", str(silence_dur),
            silence_wav
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        # 2. concat 原音频 + 静音
        cmd = [
            get_ffmpeg(), "-y",
            "-i", output_mp3,
            "-i", silence_wav,
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
            "-map", "[out]", "-ar", sr, "-ac", ch,
            tmp
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        # 3. wav → mp3
        cmd = [
            get_ffmpeg(), "-y", "-i", tmp,
            "-codec:a", "libmp3lame", "-b:a", "192k",
            output_mp3
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        # 清理
        for p in (silence_wav, tmp):
            if Path(p).exists():
                Path(p).unlink()


# =============================================================================
# 主流程
# =============================================================================

def dub_video(video_path: str, srt_path: str, output_path: str = None,
              voice: str = "zh-CN-XiaoxiaoNeural",
              rate: str = "+0%", pitch: str = "+0Hz",
              sample: int = 0,
              reference_audio: str = None,
              reference_text: str = None) -> str:
    """
    给视频配音。
    sample > 0 时：只合成前 N 条做试听，不合并视频。
    """
    if output_path is None:
        output_path = str(Path(video_path).with_name(
            Path(video_path).stem + f".dub.mp4"
        ))

    engine = detect_engine(voice)
    print(f"Engine: {engine}, Voice: {voice}")

    cues = parse_srt(srt_path)
    print(f"Loaded {len(cues)} cues from SRT")

    if sample > 0:
        cues = cues[:sample]
        print(f"Sample mode: only synthesizing first {sample} cues")

    # 临时目录
    work_dir = Path(video_path).parent / ".dub_work"
    ensure_dir(str(work_dir))

    # 1. 逐条合成
    raw_files = []
    aligned_files = []
    for i, cue in enumerate(cues, 1):
        raw_mp3 = work_dir / f"raw_{i:03d}.mp3"
        aligned_mp3 = work_dir / f"seg_{i:03d}.mp3"
        target_dur = cue["end"] - cue["start"]
        text = cue["text"].replace("\n", " ")

        print(f"[{i}/{len(cues)}] Synth: {text[:30]}...")

        if engine == "edge-tts":
            asyncio.run(edge_tts_synthesize(text, voice, str(raw_mp3), rate, pitch))
        elif engine == "voxcpm":
            voxcpm_synthesize(text, voice, str(raw_mp3),
                              reference_audio, reference_text)
        elif engine == "mmx":
            mmx_synthesize(text, voice, str(raw_mp3))
        else:
            raise ValueError(f"Unknown engine: {engine}")

        # 时长对齐
        align_to_target(str(raw_mp3), str(aligned_mp3), target_dur)
        raw_files.append(raw_mp3)
        aligned_files.append(aligned_mp3)

    if sample > 0:
        print(f"\n[Sample mode] Generated {len(aligned_files)} clips in {work_dir}")
        print("Listen to them, then re-run without --sample to dub full video")
        return str(work_dir)

    # 2. 拼接（按 SRT 顺序，cue 之间补静音到 SRT 边界）
    concat_list = work_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for af in aligned_files:
            f.write(f"file '{af.resolve()}'\n")

    merged_audio = work_dir / "merged.mp3"
    cmd = [
        get_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(merged_audio)
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # 3. 把合并音频 mplex 回视频
    # 先把合并音频 padding 到视频总时长
    video_dur_cmd = [
        get_ffprobe(), "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path
    ]
    video_dur = float(subprocess.run(video_dur_cmd, capture_output=True,
                                     text=True, check=True).stdout.strip())
    merged_dur = get_audio_duration(str(merged_audio))

    final_audio = work_dir / "final.mp3"
    if merged_dur < video_dur:
        # 补静音
        pad_dur = video_dur - merged_dur
        cmd = [
            get_ffmpeg(), "-y", "-i", str(merged_audio),
            "-f", "lavfi", "-t", str(pad_dur), "-i", "anullsrc=r=24000:cl=mono",
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
            "-map", "[out]", str(final_audio)
        ]
    else:
        # 截断
        cmd = [
            get_ffmpeg(), "-y", "-i", str(merged_audio),
            "-t", str(video_dur),
            "-c", "copy", str(final_audio)
        ]
    subprocess.run(cmd, check=True, capture_output=True)

    # 4. mplex
    cmd = [
        get_ffmpeg(), "-y", "-i", video_path, "-i", str(final_audio),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    print(f"\n[OK] Dubbed video: {output_path}")
    return output_path


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="aping-dubbing-video: 视频+SRT → 配音视频"
    )
    parser.add_argument("video", help="输入视频路径")
    parser.add_argument("--srt", required=True, help="目标语言 SRT 路径")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural",
                        help="voice ID（自动选引擎）")
    parser.add_argument("--rate", default="+0%", help="语速（edge-tts）")
    parser.add_argument("--pitch", default="+0Hz", help="音调（edge-tts）")
    parser.add_argument("--reference_audio", default=None,
                        help="VoxCPM 克隆参考音频")
    parser.add_argument("--reference_text", default=None,
                        help="参考音频的文本（VoxCPM）")
    parser.add_argument("--sample", type=int, default=0,
                        help="只合成前 N 条做试听（不合并）")
    parser.add_argument("--out", default=None, help="输出路径")
    args = parser.parse_args()

    dub_video(
        video_path=args.video,
        srt_path=args.srt,
        output_path=args.out,
        voice=args.voice,
        rate=args.rate,
        pitch=args.pitch,
        sample=args.sample,
        reference_audio=args.reference_audio,
        reference_text=args.reference_text,
    )


if __name__ == "__main__":
    main()
