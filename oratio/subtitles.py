"""제목/가사/크레딧을 ASS 자막 파일로 만든다. (FFmpeg 이 영상 위에 그려 준다)"""

from __future__ import annotations

from pathlib import Path

from .song import Meta
from .style import Style
from .timing import Cue


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> ASS 의 '&HAABBGGRR'."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(t, 0.0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _text(s: str, split: bool = False) -> str:
    """ASS 특수문자 처리. split=True 이면 가사의 ' / ' 를 화면 안 줄바꿈으로 바꾼다."""
    s = s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return s.replace(" / ", "\\N") if split else s


def _text_width(s: str) -> float:
    """글자 크기 1 기준 대략적인 줄 너비. 한글·한자는 1, 공백·영문·숫자는 그보다 좁다."""
    w = 0.0
    for ch in s:
        if ch == " ":
            w += 0.3
        elif ord(ch) < 0x1100:
            w += 0.55
        else:
            w += 1.0
    return max(w, 1.0)


def build_ass(path: Path, cues: list[Cue], meta: Meta, style: Style, total: float) -> None:
    W, H = style.width, style.height
    white = _ass_color(style.lyric_color)
    outline = _ass_color(style.lyric_outline)
    shadow = _ass_color("#000000", 0x60)
    dim = _ass_color("#FFFFFF", 0x50)

    lyric_align = 2 if style.lyric_position == "bottom" else 5
    lyric_margin_v = int(H * 0.12) if style.lyric_position == "bottom" else 0

    # Name, Font, Size, Primary, Secondary, Outline, Back, Bold, Italic, Underline, StrikeOut,
    # ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    def sty(name, font, size, color, bold, outline_w, shadow_w, align, margin_v):
        return (
            f"Style: {name},{font},{size},{color},{color},{outline},{shadow},{bold},0,0,0,"
            f"100,100,1,0,1,{outline_w},{shadow_w},{align},{int(W*0.06)},{int(W*0.06)},{margin_v},1"
        )

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 2",  # 자동 줄바꿈 없음: 가사는 항상 한 줄 (넘치면 글자를 줄인다)
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        sty("Lyric", style.font, style.lyric_size, white, 0, 3, 2, lyric_align, lyric_margin_v),
        sty("Title", style.title_font, style.title_size, white, -1, 3, 3, 5, 0),
        sty("Sub", style.font, style.subtitle_size, white, 0, 2, 2, 5, 0),
        sty("Credit", style.font, style.credit_size, white, 0, 2, 2, 5, 0),
        sty("Corner", style.font, 34, dim, 0, 1, 0, 7, int(H * 0.05)),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: list[str] = []

    def add(start, end, style_name, text, fade=style.fade_ms, layer=0):
        if end - start < 0.2:
            return
        events.append(
            f"Dialogue: {layer},{_ts(start)},{_ts(end)},{style_name},,0,0,0,,{{\\fad({fade},{fade})}}{text}"
        )

    first = cues[0].start if cues else total
    last = cues[-1].end if cues else 0.0

    # 1) 인트로: 제목 + 부제 + 성가대
    intro_end = min(first - 0.3, style.intro_max_seconds)
    if intro_end >= 2.0:
        cy = H // 2
        add(0.3, intro_end, "Title", f"{{\\pos({W//2},{cy - 30})}}{_text(meta.title)}", 800)
        lines = [x for x in (meta.subtitle, meta.choir) if x]
        for i, line in enumerate(lines):
            add(0.8, intro_end, "Sub", f"{{\\pos({W//2},{cy + 90 + i * 70})}}{_text(line)}", 800)

    # 2) 가사가 나오는 동안 왼쪽 위에 작게 곡 제목 표시
    corner = " · ".join(x for x in (meta.title, meta.choir) if x)
    if cues:
        add(max(first - 0.5, 0), last, "Corner", _text(corner), 1000)

    # 3) 가사 — 화면 폭을 넘으면 글자 크기를 줄여 한 줄로 유지
    max_w = W * 0.88
    for cue in cues:
        text = cue.text.replace(" / ", " ")
        width = _text_width(text) * style.lyric_size
        fs = f"{{\\fs{int(style.lyric_size * max_w / width)}}}" if width > max_w else ""
        add(cue.start, cue.end, "Lyric", fs + _text(text))

    # 4) 아웃트로: 성경 구절 + 크레딧
    outro_start = last + 0.6
    if total - outro_start >= 2.0:
        blocks = []
        if meta.verse:
            blocks.append(("Sub", meta.verse))
        blocks += [("Credit", c) for c in meta.credits]
        if meta.choir:
            blocks.append(("Credit", meta.choir))
        if blocks:
            gap = 80
            y0 = H // 2 - (len(blocks) - 1) * gap // 2
            for i, (st, text) in enumerate(blocks):
                if st == "Sub":  # 구절과 크레딧 사이를 조금 띄운다
                    y = y0 + i * gap - 30
                else:
                    y = y0 + i * gap + (30 if meta.verse else 0)
                add(outro_start + i * 0.3, total - 0.2, st, f"{{\\pos({W//2},{y})}}{_text(text)}", 800)

    path.write_text("\n".join(header + events) + "\n", encoding="utf-8")
