"""
aping-common: 共享配置和工具函数

被所有 aping-* skill 引用。提供：
- 默认 ffmpeg / ffprobe 路径
- Windows 兼容字体
- 路径处理
- 时间戳格式化（SRT <-> 秒）
- ffmpeg 工具函数
"""

import os
import re
import sys
import shutil
import subprocess
import json
from pathlib import Path
from typing import Optional, List, Tuple


# =============================================================================
# Windows 控制台 UTF-8 修复 (在 main() 入口调一次)
# =============================================================================

def setup_console(verbose: bool = False):
    """
    修复 Windows 控制台 GBK 乱码，让 print 中文不乱码。
    在 Python 3.7+ Windows 下重新设置 stdout/stderr 编码为 utf-8。
    必须在 main() 入口最顶部调用。
    """
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    if verbose:
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(message)s",
            datefmt="%H:%M:%S",
        )


def log(msg: str, verbose: bool = False, level: str = "INFO"):
    """
    简易日志输出: 控制台才 verbose=True 时才打印。
    可被覆盖到文件。
    """
    if verbose or level == "ERROR":
        # 测距 颜文字 emoji 让进度更明显
        prefix = {"INFO": "  ", "STEP": ">", "OK": "✓", "ERR": "✗"}.get(level, " ")
        print(f"{prefix} {msg}", flush=True)


# =============================================================================
# 路径与配置
# =============================================================================

# 项目根目录（aping-common/aping-common/aping_common.py -> 上 3 级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认输出根目录（用户可覆盖）
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

# Windows 兼容字体（用于 ffmpeg libass 烧字幕）
WINDOWS_CJK_FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",    # 微软雅黑 Bold
    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
    r"C:\Windows\Fonts\simsun.ttc",    # 宋体
]


def get_ffmpeg() -> str:
    """获取 ffmpeg 可执行路径"""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    candidates = [
        r"C:\Users\shuis\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError("ffmpeg not found in PATH or known locations")


def get_ffprobe() -> str:
    """获取 ffprobe 可执行路径（与 ffmpeg 同目录）"""
    ffmpeg = get_ffmpeg()
    # Windows 上可能是 .EXE 大小写不敏感，逐个尝试
    ffmpeg_dir = Path(ffmpeg).parent
    for name in os.listdir(ffmpeg_dir):
        if name.lower() == "ffprobe.exe":
            return str(ffmpeg_dir / name)
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe
    raise FileNotFoundError("ffprobe not found in ffmpeg directory or PATH")


def get_cjk_font() -> str:
    """获取可用的 CJK 字体文件名（用于 libass force_style）"""
    for f in WINDOWS_CJK_FONTS:
        if os.path.exists(f):
            return Path(f).stem
    raise FileNotFoundError("No CJK font found in C:/Windows/Fonts/")


# =============================================================================
# 时间戳与 SRT 工具
# =============================================================================

def seconds_to_srt_time(seconds: float) -> str:
    """秒数 -> SRT 时间戳格式 HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        millis = 0
        secs += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt_time_to_seconds(time_str: str) -> float:
    """SRT 时间戳 HH:MM:SS,mmm -> 秒数"""
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        return float(parts[0])
    return int(h) * 3600 + int(m) * 60 + float(s)


# =============================================================================
# SRT 解析与生成
# =============================================================================

def parse_srt(srt_path: str) -> list:
    """
    解析 SRT 文件为 cue 列表
    返回: [{"index": 1, "start": 0.0, "end": 3.5, "text": "你好"}, ...]
    """
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    cues = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue
        time_line = lines[1]
        match = re.match(
            r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)",
            time_line,
        )
        if not match:
            continue
        start = srt_time_to_seconds(match.group(1))
        end = srt_time_to_seconds(match.group(2))
        text = "\n".join(lines[2:]).strip()
        cues.append({
            "index": index,
            "start": start,
            "end": end,
            "text": text,
        })
    return cues


def write_srt(cues: list, srt_path: str):
    """
    写 SRT 文件
    cues 元素需要有: start, end, text（index 可选，会自动重新编号）
    """
    with open(srt_path, "w", encoding="utf-8-sig") as f:
        for i, cue in enumerate(cues, 1):
            start = seconds_to_srt_time(cue["start"])
            end = seconds_to_srt_time(cue["end"])
            text = cue["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


# =============================================================================
# ffmpeg 工具函数
# =============================================================================

def run_ffmpeg(args: list, check: bool = True) -> subprocess.CompletedProcess:
    """
    调 ffmpeg，自动加 -hide_banner -y
    """
    cmd = [get_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"FFmpeg stderr: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed with code {result.returncode}")
    return result


def get_video_info(video_path: str) -> dict:
    """用 ffprobe 查视频元数据"""
    cmd = [
        get_ffprobe(),
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def get_duration(video_path: str) -> float:
    """获取音视频时长（秒）"""
    info = get_video_info(video_path)
    return float(info["format"]["duration"])


def get_resolution(video_path: str) -> Tuple[int, int]:
    """获取视频分辨率 (width, height)"""
    info = get_video_info(video_path)
    for stream in info["streams"]:
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise ValueError("No video stream found")


# =============================================================================
# 工具函数
# =============================================================================

def ensure_dir(path: str):
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)


def probe_duration(path: str) -> float:
    """get_duration 的别名（更口语化）"""
    return get_duration(path)


def safe_filename(text: str, max_len: int = 50) -> str:
    """把文本变成安全的文件名（去特殊字符，截断）"""
    # 保留中文（CJK 基本+扩展A）、字母、数字、连字符、下划线
    safe = re.sub(r"[^\w\u4e00-\u9fff\u3400-\u4dbf\-]+", "-", text.strip())
    safe = re.sub(r"-+", "-", safe).strip("-")
    if len(safe) > max_len:
        safe = safe[:max_len]
    return safe or "untitled"


# 让 seconds_to_srt_time 也能叫 format_srt_time_srt
format_srt_time_srt = seconds_to_srt_time
