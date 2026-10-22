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


def _scene_inputs(images: list[Path], starts: list[float], style: Style, total: float,
                  fade: float) -> tuple[list[str], str, int]:
    """장면 그림 여러 장을 시간에 맞춰 이어 붙이고, 바뀔 때 서서히 겹치게(xfade) 한다.

    i 번째 그림은 (starts[i] - fade/2) ~ (starts[i+1] + fade/2) 동안 보인다.
    """
    W, H, fps = style.width, style.height, style.fps
    bw, bh = int(W * 1.1) // 2 * 2, int(H * 1.1) // 2 * 2
    n = len(images)
    bounds = list(starts) + [total]
    args: list[str] = []
    parts: list[str] = []
    for i, img in enumerate(images):
        begin = 0.0 if i == 0 else bounds[i] - fade / 2
        end = bounds[i + 1] + (fade / 2 if i < n - 1 else 1.0)
        args += ["-loop", "1", "-framerate", str(fps), "-t", f"{end - begin:.3f}", "-i", str(img)]
        # 장면마다 움직이는 방향을 바꾼다
        sx, sy = (1, 1) if i % 2 == 0 else (-1, 1)
        move = (f"crop={W}:{H}:x='(iw-ow)/2*(1+{sx}*0.9*sin(t/19))':y='(ih-oh)/2*(1+{sy}*0.9*sin(t/27))'"
                if style.background_motion else f"crop={W}:{H}")
        parts.append(f"[{i}:v]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                     f"{move},fps={fps},setsar=1,format=yuv420p[s{i}]")
    last = "s0"
    for i in range(1, n):
        parts.append(f"[{last}][s{i}]xfade=transition=fade:duration={fade}:offset={bounds[i] - fade / 2:.3f}[x{i}]")
        last = f"x{i}"
    parts.append(f"[{last}]null")
    return args, ";".join(parts), n


def render(song: Song, style: Style, ass_file: Path, total: float, output: Path,
           start: float = 0.0, length: float | None = None, fast: bool = False,
           scenes: tuple[list[Path], list[float]] | None = None, fade: float = 2.0) -> None:
    build = ass_file.parent
    if scenes:
        bg_args, chain, n_inputs = _scene_inputs(scenes[0], scenes[1], style, total, fade)
        dim = style.scene_dim
    else:
        bg_args, chain = _background_inputs(song, style, total)
        n_inputs = 1
        dim = style.background_dim if song.background is not None else 0.0  # 기본 그라데이션은 이미 어둡다

    if style.background_blur > 0:
        chain += f",boxblur={int(style.background_blur)}:1"
    k = max(0.0, min(1.0, 1.0 - float(dim)))
    if k < 1.0:
        chain += f",colorchannelmixer=rr={k:.3f}:gg={k:.3f}:bb={k:.3f}"
    chain += ",vignette=PI/5"

    subs = f"ass={_filter_path(ass_file, build)}"
    if FONTS_DIR.exists():
        subs += f":fontsdir={_filter_path(FONTS_DIR, build)}"
    chain += f",{subs},format=yuv420p[v]"

    args = [*bg_args, "-i", str(song.audio), "-filter_complex", chain,
            "-map", "[v]", "-map", f"{n_inputs}:a"]
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
