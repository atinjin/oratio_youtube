"""가사 타이밍 만들기, 그리고 LRC 파일로 저장/읽기.

timing.lrc 형식 (사람이 메모장으로 고칠 수 있게 단순하게 유지):

    [00:12.50]주님의 은혜 넘치네
    [00:17.20]내 잔이 넘치네
    [00:21.00]                <- 내용 없는 줄 = 이 시각에 가사 지우기 (간주 등)

각 줄은 다음 줄의 시각까지 화면에 보인다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .media import audio_duration
from .song import Song


@dataclass
class Cue:
    start: float
    end: float
    text: str


# 마지막 줄 뒤에 끝 표시가 없을 때 보여줄 최대 시간.
MAX_CUE_SECONDS = 12.0


def _fmt(t: float) -> str:
    m, s = divmod(max(t, 0.0), 60)
    return f"{int(m):02d}:{s:05.2f}"


def write_lrc(path: Path, cues: list[Cue]) -> None:
    out = [
        "# 가사 타이밍 파일입니다. [분:초] 를 고친 뒤 다시 render 하면 반영됩니다.",
        "# 내용 없는 [분:초] 줄은 그 시각에 가사를 화면에서 내립니다.",
    ]
    for i, cue in enumerate(cues):
        out.append(f"[{_fmt(cue.start)}]{cue.text}")
        nxt = cues[i + 1].start if i + 1 < len(cues) else None
        if nxt is None or nxt - cue.end > 0.05:
            out.append(f"[{_fmt(cue.end)}]")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


_LRC_LINE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")


def read_lrc(path: Path, total: float) -> list[Cue]:
    marks: list[tuple[float, str]] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LRC_LINE.match(line)
        if not m:
            print(f"[경고] timing.lrc 에서 읽을 수 없는 줄을 건너뜁니다: {line}")
            continue
        marks.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))
    marks.sort(key=lambda x: x[0])

    cues = []
    for i, (start, text) in enumerate(marks):
        if not text:
            continue
        end = marks[i + 1][0] if i + 1 < len(marks) else min(start + MAX_CUE_SECONDS, total)
        cues.append(Cue(start, end, text))
    return cues


def even_timing(song: Song, total: float) -> list[Cue]:
    """음성 인식 없이, 글자 수에 비례해 가사 시간을 나눈다.

    전주/후주 구간은 meta.yaml 의 lyrics_start / lyrics_end 로 지정할 수 있다.
    """
    start = song.meta.lyrics_start
    end = song.meta.lyrics_end
    if start is None:
        start = min(max(total * 0.08, 5.0), 20.0)
    if end is None:
        end = total - min(max(total * 0.06, 4.0), 15.0)
    if end <= start:
        start, end = 0.0, total

    weights = [max(len(line.replace(" ", "")), 4) for line in song.lyrics]
    scale = (end - start) / sum(weights)
    cues, t = [], start
    for line, w in zip(song.lyrics, weights):
        dur = w * scale
        cues.append(Cue(t, t + dur, line))
        t += dur
    return cues


def whisper_timing(song: Song, model_name: str = "medium", separate_vocals: bool = False) -> list[Cue]:
    """stable-ts(Whisper)로 이미 있는 가사를 음원에 맞춰 정렬한다."""
    try:
        import stable_whisper  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Whisper 정렬을 쓰려면 먼저 설치해 주세요:  pip install -r requirements-whisper.txt\n"
            "설치 없이 해보려면 --align even 을 쓰면 됩니다."
        ) from exc

    print(f"[정렬] Whisper '{model_name}' 모델을 불러옵니다. 처음에는 다운로드 시간이 걸립니다...")
    model = stable_whisper.load_model(model_name)
    text = "\n".join(line.replace(" / ", " ") for line in song.lyrics)

    kwargs = dict(language="ko", original_split=True)
    if separate_vocals:
        kwargs["denoiser"] = "demucs"  # 반주를 걷어내고 목소리로만 정렬
    try:
        result = model.align(str(song.audio), text, **kwargs)
    except TypeError:
        # 오래된 stable-ts 버전 호환
        kwargs.pop("denoiser", None)
        if separate_vocals:
            kwargs["demucs"] = True
        result = model.align(str(song.audio), text, **kwargs)

    segments = list(result.segments)
    if len(segments) != len(song.lyrics):
        print(
            f"[경고] 정렬된 줄 수({len(segments)})가 가사 줄 수({len(song.lyrics)})와 다릅니다. "
            "timing.lrc 를 확인해 주세요."
        )
    cues = []
    for i, seg in enumerate(segments):
        # 화면에는 원래 가사(줄바꿈 표시 ' / ' 포함)를 보여준다.
        label = song.lyrics[i] if i < len(song.lyrics) else seg.text.strip()
        cues.append(Cue(float(seg.start), float(seg.end), label))
    return cues


def smooth(cues: list[Cue]) -> list[Cue]:
    """가사가 너무 빨리 사라지지 않도록 다음 줄 직전까지 늘리고, 겹침을 없앤다."""
    cues = sorted(cues, key=lambda c: c.start)
    for i, cue in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else None
        if nxt is not None:
            gap = nxt - cue.end
            if gap < 0:
                cue.end = nxt
            elif gap < 2.0:  # 짧은 숨 쉬는 구간은 이어서 보여준다
                cue.end = nxt
        cue.end = max(cue.end, cue.start + 1.0)
    return cues


def _installed(module: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(module) is not None


def _auto_mode(song: Song) -> str:
    """목소리 트랙이 있으면 그걸로, 아니면 설치된 도구에 따라 고른다."""
    from .vocals import find_vocals

    if find_vocals(song):
        return "vocals"
    if _installed("stable_whisper"):
        return "whisper"
    if _installed("sherpa_onnx") and _installed("soundfile"):
        return "vocals"
    print("[정렬] Whisper / 목소리 분리 도구가 없어 균등 분배로 타이밍을 만듭니다.")
    return "even"


def get_cues(song: Song, mode: str, model_name: str, separate_vocals: bool, retime: bool) -> list[Cue]:
    total = audio_duration(song.audio)

    if song.timing_file.exists() and not retime:
        print(f"[정렬] 저장된 타이밍을 사용합니다: {song.timing_file.name} (새로 만들려면 --retime)")
        cues = read_lrc(song.timing_file, total)
        from .vocals import find_vocals, sung_regions, trim_to_vocals
        vocals = find_vocals(song)
        if vocals:
            n = trim_to_vocals(cues, sung_regions(vocals))
            if n:
                print(f"[정렬] 목소리 트랙 기준으로 간주 {n}곳에서 가사를 자동으로 내립니다.")
        return cues

    if mode == "auto":
        mode = _auto_mode(song)

    if mode == "whisper":
        cues = whisper_timing(song, model_name, separate_vocals)
    elif mode == "vocals":
        from .vocals import vocals_timing
        cues = vocals_timing(song)
    else:
        cues = even_timing(song, total)
    cues = smooth(cues)
    write_lrc(song.timing_file, cues)
    print(f"[정렬] 타이밍을 저장했습니다: {song.timing_file}  (틀린 곳은 이 파일을 고친 뒤 다시 render)")
    return cues
