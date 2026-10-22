"""영상 스타일 기본값. 곡 폴더에 style.yaml 을 두면 일부 값만 덮어쓸 수 있다."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


@dataclass
class Style:
    width: int = 1920
    height: int = 1080
    fps: int = 30

    # 폰트는 fonts/ 폴더에 넣은 파일의 '글꼴 이름'을 쓴다. (README 참고)
    # 가변 폰트(파일 이름에 [wght] 가 붙은 것)는 인식이 잘 안 되니 일반 폰트 파일을 쓴다.
    font: str = "NanumMyeongjo"
    title_font: str = "NanumMyeongjo"

    lyric_size: int = 72
    lyric_color: str = "#FFFFFF"
    lyric_outline: str = "#000000"
    lyric_position: str = "bottom"   # bottom | center
    title_size: int = 110
    subtitle_size: int = 48
    credit_size: int = 44

    fade_ms: int = 400               # 가사 페이드 인/아웃
    intro_max_seconds: float = 7.0   # 첫 가사 전 제목 화면 최대 길이
    background_dim: float = 0.45     # 배경 어둡게 (0 = 그대로, 1 = 검정)
    background_blur: int = 0         # 배경 흐림 정도 (0 = 끔)
    background_motion: bool = True   # 배경 천천히 움직이기

    crf: int = 20                    # 화질 (낮을수록 고화질, 18~23 권장)
    preset: str = "medium"           # 인코딩 속도 (ultrafast ~ slow)


def load_style(folder: Path) -> Style:
    style = Style()
    path = folder / "style.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
        names = {f.name for f in fields(Style)}
        for key, value in data.items():
            if key in names:
                setattr(style, key, value)
            else:
                print(f"[경고] style.yaml 에서 알 수 없는 항목은 무시합니다: {key}")
    return style
