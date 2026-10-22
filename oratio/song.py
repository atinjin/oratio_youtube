"""곡 폴더(음원, 가사, 메타데이터, 배경)를 읽어 들인다."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")


@dataclass
class Meta:
    title: str
    subtitle: str = ""          # 예: 2026년 10월 25일 주일예배 특송
    choir: str = ""             # 예: 오라티오 성가대
    credits: list[str] = field(default_factory=list)  # 예: ["작사·작곡 홍길동", "지휘 김OO"]
    verse: str = ""             # 아웃트로에 보여줄 성경 구절
    # 균등 분배 모드에서 가사가 시작/끝나는 시각(초). 비우면 자동으로 정한다.
    lyrics_start: float | None = None
    lyrics_end: float | None = None


@dataclass
class Song:
    folder: Path
    audio: Path
    lyrics: list[str]           # 화면 한 장면 = 한 줄 (" / "는 화면 안 줄바꿈)
    meta: Meta
    background: Path | None

    @property
    def timing_file(self) -> Path:
        return self.folder / "timing.lrc"

    @property
    def build_dir(self) -> Path:
        return self.folder / "build"


def _find(folder: Path, stem: str, exts: tuple[str, ...]) -> Path | None:
    for ext in exts:
        for candidate in (folder / f"{stem}{ext}", folder / f"{stem}{ext.upper()}"):
            if candidate.exists():
                return candidate
    return None


def read_lyrics(path: Path) -> list[str]:
    """빈 줄과 '#'으로 시작하는 줄(메모)은 건너뛴다."""
    lines = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_song(folder: str | Path) -> Song:
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise SystemExit(f"곡 폴더를 찾을 수 없습니다: {folder}")

    audio = _find(folder, "audio", AUDIO_EXTS)
    if audio is None:
        raise SystemExit(f"음원 파일이 없습니다. {folder}/audio.mp3 처럼 넣어 주세요.")

    lyrics_path = folder / "lyrics.txt"
    if not lyrics_path.exists():
        raise SystemExit(f"가사 파일이 없습니다: {lyrics_path}")
    lyrics = read_lyrics(lyrics_path)
    if not lyrics:
        raise SystemExit("lyrics.txt 에 가사가 비어 있습니다.")

    meta_path = folder / "meta.yaml"
    data = {}
    if meta_path.exists():
        data = yaml.safe_load(meta_path.read_text(encoding="utf-8-sig")) or {}
    data.setdefault("title", folder.name)
    known = Meta.__dataclass_fields__.keys()
    unknown = set(data) - set(known)
    if unknown:
        print(f"[경고] meta.yaml 에서 알 수 없는 항목은 무시합니다: {', '.join(sorted(unknown))}")
    meta = Meta(**{k: v for k, v in data.items() if k in known})
    meta.credits = [str(c) for c in (meta.credits or [])]

    background = _find(folder, "background", IMAGE_EXTS + VIDEO_EXTS)
    return Song(folder=folder, audio=audio, lyrics=lyrics, meta=meta, background=background)
