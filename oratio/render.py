"""배경 + 자막 + 음원을 FFmpeg 으로 합쳐 MP4 를 만든다."""

from __future__ import annotations

import os
from pathlib import Path

from .media import run_ffmpeg
from .song import VIDEO_EXTS, Song
from .style import Style

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"


def _filter_path(target: Path, cwd: Path) -> str:
    """필터 옵션 안에 넣을 경로. 가능하면 상대 경로로 써서 Windows 의 'C:' 이스케이프 문제를 피한다."""
    try:
        p = os.path.relpath(target, cwd)
    except ValueError:  # Windows 에서 드라이브가 다를 때
        p = str(target)
    p = p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"'{p}'"


def _background_inputs(song: Song, style: Style, total: float) -> tuple[list[str], str]:
    """배경 입력 인자와, 배경을 W x H 로 맞추는 필터 체인을 돌려준다."""
    W, H, fps = style.width, style.height, style.fps
    bg = song.background

    if bg is None:
        # 배경 파일이 없으면 천천히 변하는 어두운 그라데이션을 만든다.
        args = ["-f", "lavfi", "-i",
                f"gradients=s={W}x{H}:r={fps}:c0=0x1d2b53:c1=0x4b2c5e:c2=0x0f1a2e:n=3:speed=0.004:d={total + 1:.2f}"]
        return args, "[0:v]setsar=1"

    is_video = bg.suffix.lower() in VIDEO_EXTS
    if is_video:
        args = ["-stream_loop", "-1", "-i", str(bg)]
    else:
        args = ["-loop", "1", "-framerate", str(fps), "-i", str(bg)]

    if style.background_motion and not is_video:
        # 10% 크게 키운 뒤, 아주 천천히 좌우/위아래로 움직인다 (Ken Burns 느낌).
        bw, bh = int(W * 1.1) // 2 * 2, int(H * 1.1) // 2 * 2
        chain = (
            f"[0:v]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
            f"crop={W}:{H}:x='(iw-ow)/2*(1+sin(t/23))':y='(ih-oh)/2*(1+sin(t/31))',"
            f"fps={fps},setsar=1"
        )
    else:
        chain = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"fps={fps},setsar=1"
        )
    return args, chain


def render(song: Song, style: Style, ass_file: Path, total: float, output: Path,
           start: float = 0.0, length: float | None = None, fast: bool = False) -> None:
    build = ass_file.parent
    bg_args, chain = _background_inputs(song, style, total)

    if style.background_blur > 0:
        chain += f",boxblur={int(style.background_blur)}:1"
    k = max(0.0, min(1.0, 1.0 - float(style.background_dim)))
    if k < 1.0 and song.background is not None:  # 기본 그라데이션은 이미 어둡다
        chain += f",colorchannelmixer=rr={k:.3f}:gg={k:.3f}:bb={k:.3f}"
    chain += ",vignette=PI/5"

    subs = f"ass={_filter_path(ass_file, build)}"
    if FONTS_DIR.exists():
        subs += f":fontsdir={_filter_path(FONTS_DIR, build)}"
    chain += f",{subs},format=yuv420p[v]"

    args = [*bg_args, "-i", str(song.audio), "-filter_complex", chain,
            "-map", "[v]", "-map", "1:a"]
    if start > 0:
        args += ["-ss", f"{start:.2f}"]
    duration = (min(length, total - start) if length else total - start)
    args += [
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast" if fast else style.preset,
        "-crf", str(style.crf + (6 if fast else 0)),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ]
    print(f"[렌더링] {output.name} 만드는 중... ({duration:.0f}초 분량)")
    run_ffmpeg(args, cwd=build)


def thumbnail(video: Path, at: float, output: Path) -> None:
    run_ffmpeg(["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-update", "1", "-q:v", "2", str(output)],
               cwd=video.parent)
