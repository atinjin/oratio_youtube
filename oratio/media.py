"""FFmpeg / FFprobe 호출 도우미."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise SystemExit(
            f"{', '.join(missing)} 를 찾을 수 없습니다.\n"
            "  Windows: winget install Gyan.FFmpeg   (설치 후 터미널을 새로 여세요)\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg"
        )


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def run_ffmpeg(args: list[str], cwd: Path) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y", *args]
    proc = subprocess.run(cmd, cwd=cwd)
    if proc.returncode != 0:
        raise SystemExit(f"FFmpeg 실행에 실패했습니다 (코드 {proc.returncode}).")
