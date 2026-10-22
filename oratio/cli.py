"""명령줄 진입점.

    python -m oratio fonts                                  # 기본 한글 폰트 받기 (처음 한 번)
    python -m oratio new    songs/2026-10-25_주님의은혜     # 곡 폴더 틀 만들기
    python -m oratio render songs/2026-10-25_주님의은혜     # 영상 만들기
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .media import audio_duration, require_ffmpeg
from .render import FONTS_DIR, render, thumbnail
from .song import load_song
from .style import load_style
from .subtitles import build_ass
from .timing import get_cues

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "songs" / "example"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/nanummyeongjo/NanumMyeongjo-{}.ttf"


def cmd_fonts(args: argparse.Namespace) -> None:
    """기본 폰트(나눔명조, 무료 OFL 라이선스)를 fonts/ 폴더에 받는다."""
    import urllib.request

    FONTS_DIR.mkdir(exist_ok=True)
    for weight in ("Regular", "Bold"):
        target = FONTS_DIR / f"NanumMyeongjo-{weight}.ttf"
        if target.exists():
            print(f"이미 있습니다: {target.name}")
            continue
        print(f"받는 중: {target.name}")
        urllib.request.urlretrieve(FONT_URL.format(weight), target)
    print(f"완료: {FONTS_DIR}")


def check_fonts(style) -> None:
    files = [p for p in FONTS_DIR.glob("*") if p.suffix.lower() in (".ttf", ".otf", ".ttc")]
    if not files:
        print("[경고] fonts/ 폴더에 폰트가 없습니다. 한글이 다른 글꼴로 보일 수 있습니다.")
        print("       python -m oratio fonts  로 기본 폰트(나눔명조)를 받아 주세요.")


def cmd_new(args: argparse.Namespace) -> None:
    folder = Path(args.folder)
    if folder.exists() and any(folder.iterdir()):
        raise SystemExit(f"이미 내용이 있는 폴더입니다: {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("meta.yaml", "lyrics.txt"):
        shutil.copy(TEMPLATE_DIR / name, folder / name)
    print(f"곡 폴더를 만들었습니다: {folder}")
    print("  1) audio.mp3 (음원)을 넣고")
    print("  2) meta.yaml, lyrics.txt 를 고친 뒤")
    print("  3) (선택) background.jpg 또는 background.mp4 를 넣고")
    print(f"  4) python -m oratio render {folder}")


def write_description(song, path: Path) -> None:
    m = song.meta
    parts = [m.title]
    if m.subtitle:
        parts.append(m.subtitle)
    if m.choir:
        parts.append(m.choir)
    parts.append("")
    if m.credits:
        parts += m.credits + [""]
    if m.verse:
        parts += [m.verse, ""]
    parts.append("[가사]")
    parts += [line.replace(" / ", " ") for line in song.lyrics]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def cmd_render(args: argparse.Namespace) -> None:
    require_ffmpeg()
    song = load_song(args.folder)
    style = load_style(song.folder)
    if args.vertical:
        style.width, style.height = 1080, 1920
        style.lyric_position = "center"
    check_fonts(style)
    song.build_dir.mkdir(exist_ok=True)
    total = audio_duration(song.audio)

    print(f"[곡] {song.meta.title}  ({total:.0f}초, 가사 {len(song.lyrics)}줄, "
          f"배경: {song.background.name if song.background else '기본 그라데이션'})")

    cues = get_cues(song, args.align, args.model, args.vocals, args.retime)
    if args.timing_only:
        return

    ass_file = song.build_dir / "lyrics.ass"
    build_ass(ass_file, cues, song.meta, style, total)

    preview = args.preview is not None
    suffix = "_preview" if preview else ("_shorts" if args.vertical else "")
    output = song.folder / f"{song.folder.name}{suffix}.mp4"
    render(song, style, ass_file, total, output,
           start=args.start, length=args.preview, fast=preview)

    if not preview:
        write_description(song, song.folder / "description.txt")
        first = cues[0].start if cues else total / 2
        thumb_at = min(max(first / 2, 1.0), style.intro_max_seconds - 1, total - 1)
        thumbnail(output, thumb_at, song.folder / "thumbnail.jpg")
        print(f"\n완성: {output}")
        print("      description.txt (유튜브 설명란), thumbnail.jpg (썸네일)도 함께 만들었습니다.")
    else:
        print(f"\n미리보기 완성: {output}")


def main(argv: list[str] | None = None) -> None:
    # Windows 콘솔에서 한글이 깨지지 않도록
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(prog="oratio", description="성가대 특송 뮤직비디오 만들기")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="새 곡 폴더 틀 만들기")
    p_new.add_argument("folder")
    p_new.set_defaults(func=cmd_new)

    p_fonts = sub.add_parser("fonts", help="기본 한글 폰트(나눔명조) 받기")
    p_fonts.set_defaults(func=cmd_fonts)

    p = sub.add_parser("render", help="영상 만들기")
    p.add_argument("folder", help="곡 폴더 (audio.mp3, lyrics.txt, meta.yaml)")
    p.add_argument("--align", choices=["auto", "vocals", "whisper", "even"], default="auto",
                   help="가사 타이밍 방법. vocals = 목소리 트랙의 노래 구간에 맞춤(합창 추천), "
                        "whisper = 음성 인식 정렬, even = 균등 분배")
    p.add_argument("--model", default="medium",
                   help="Whisper 모델 (tiny/base/small/medium/large-v3). 클수록 정확하지만 느림")
    p.add_argument("--vocals", action="store_true",
                   help="반주를 걷어내고 목소리로만 정렬 (Demucs 필요, 더 정확하지만 느림)")
    p.add_argument("--retime", action="store_true",
                   help="저장된 timing.lrc 를 무시하고 타이밍을 새로 만듦")
    p.add_argument("--timing-only", action="store_true",
                   help="timing.lrc 만 만들고 영상은 만들지 않음")
    p.add_argument("--preview", type=float, metavar="초",
                   help="앞부분 N초만 빠르게 미리보기로 만듦")
    p.add_argument("--start", type=float, default=0.0, metavar="초",
                   help="미리보기 시작 위치 (--preview 와 함께)")
    p.add_argument("--vertical", action="store_true",
                   help="세로 영상(1080x1920, 쇼츠용)으로 만듦")
    p.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
