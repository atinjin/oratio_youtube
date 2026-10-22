"""목소리 트랙으로 '노래하는 구간'을 찾아 가사를 배치한다.

합창은 여러 성부가 겹치고 반주가 깔려서 음성 인식(Whisper)이 가사를 잘 못 알아듣는다.
대신 반주를 걷어낸 목소리 트랙의 소리 크기로 노래하는 구간을 찾고,
간주를 건너뛰면서 그 구간에만 가사를 글자 수 비율대로 나눠 놓는다.

목소리 트랙은 다음 순서로 찾는다.
  1) 곡 폴더의 vocals.wav (다른 프로그램으로 분리해 둔 파일)
  2) build/vocals.wav (예전에 이 도구가 분리해 둔 파일)
  3) 없으면 sherpa-onnx + UVR 모델로 새로 분리 (requirements-vocals.txt)
"""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

import numpy as np

from .song import Song

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
UVR_MODEL = "UVR-MDX-NET-Voc_FT.onnx"
UVR_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/source-separation-models/{UVR_MODEL}"

FRAME = 0.05      # 소리 크기를 재는 단위(초)
INTERLUDE = 3.0   # 이보다 길게 쉬면 간주로 보고 가사를 내린다(초)


def find_vocals(song: Song) -> Path | None:
    for p in (song.folder / "vocals.wav", song.build_dir / "vocals.wav"):
        if p.exists():
            return p
    return None


def separate_vocals(song: Song) -> Path:
    """반주를 걷어내고 목소리만 남긴 build/vocals.wav 를 만든다."""
    try:
        import sherpa_onnx  # type: ignore
        import soundfile as sf  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "목소리 분리를 하려면 먼저 설치해 주세요:  pip install -r requirements-vocals.txt\n"
            "(또는 다른 프로그램으로 분리한 목소리 파일을 곡 폴더에 vocals.wav 로 넣어 주세요)"
        ) from exc

    model = MODELS_DIR / UVR_MODEL
    if not model.exists():
        MODELS_DIR.mkdir(exist_ok=True)
        print(f"[목소리] 분리 모델을 받는 중입니다 (약 65MB): {model.name}")
        urllib.request.urlretrieve(UVR_URL, model)

    song.build_dir.mkdir(exist_ok=True)
    wav = song.build_dir / "mix44k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(song.audio), "-ac", "2", "-ar", "44100", str(wav)],
                   check=True)
    samples, sr = sf.read(str(wav), dtype="float32", always_2d=True)

    print("[목소리] 반주와 목소리를 분리하는 중입니다. 5분 곡 기준 CPU 로 3~5분 걸립니다...")
    cfg = sherpa_onnx.OfflineSourceSeparationConfig(
        model=sherpa_onnx.OfflineSourceSeparationModelConfig(
            uvr=sherpa_onnx.OfflineSourceSeparationUvrModelConfig(model=str(model)),
            num_threads=4,
        )
    )
    out = sherpa_onnx.OfflineSourceSeparation(cfg).process(sample_rate=sr, samples=np.ascontiguousarray(samples.T))
    vocals = np.array(out.stems[0].data)  # UVR Voc_FT: 0 = 목소리, 1 = 반주
    target = song.build_dir / "vocals.wav"
    sf.write(str(target), vocals.T, out.sample_rate)
    wav.unlink(missing_ok=True)
    print(f"[목소리] 저장했습니다: {target}")
    return target


def _loudness(path: Path) -> np.ndarray:
    """FRAME 단위 소리 크기(dB)."""
    sr = 16000
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    n = int(sr * FRAME)
    frames = x[: len(x) // n * n].reshape(-1, n)
    db = 10 * np.log10(np.mean(frames ** 2, axis=1) + 1e-10)
    # 0.3초 정도로 부드럽게 해서 자음 사이의 짧은 끊김을 메운다.
    k = 6
    return np.convolve(db, np.ones(k) / k, mode="same")


def sung_regions(path: Path, min_gap: float = 0.6, min_len: float = 0.4) -> list[tuple[float, float]]:
    """노래하는 구간 [(시작, 끝), ...] 을 찾는다."""
    db = _loudness(path)
    lo, hi = np.percentile(db, 15), np.percentile(db, 95)
    on = db > lo + (hi - lo) * 0.45

    regions, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            regions.append([start * FRAME, i * FRAME])
            start = None
    if start is not None:
        regions.append([start * FRAME, len(on) * FRAME])

    merged: list[list[float]] = []
    for r in regions:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a, b) for a, b in merged if b - a >= min_len]


def place_lyrics(lines: list[str], regions: list[tuple[float, float]]):
    """노래하는 시간만 이어 붙인 축 위에 글자 수 비율로 가사를 나누고, 실제 시각으로 되돌린다."""
    from .timing import Cue

    total_sung = sum(b - a for a, b in regions)
    starts_sung = np.cumsum([0.0] + [b - a for a, b in regions])  # 각 구간이 시작하는 '노래 시간'

    def to_real(t_sung: float) -> float:
        i = int(np.searchsorted(starts_sung, t_sung, side="right") - 1)
        i = min(max(i, 0), len(regions) - 1)
        return regions[i][0] + (t_sung - starts_sung[i])

    weights = np.array([max(len(line.replace(" ", "").replace("/", "")), 3) for line in lines], dtype=float)
    bounds = np.concatenate([[0.0], np.cumsum(weights) / weights.sum() * total_sung])

    onsets = [a for a, _ in regions]
    cues = []
    for i, line in enumerate(lines):
        start = to_real(bounds[i] + 1e-6)
        # 가까운 곳(2초 이내)에 노래가 새로 시작하는 지점이 있으면 거기에 맞춘다.
        near = min(onsets, key=lambda o: abs(o - start))
        if abs(near - start) < 2.0:
            start = near
        end = to_real(bounds[i + 1] - 1e-6)
        cues.append(Cue(start, max(end, start + 1.0), line))

    # 앞 줄 끝이 다음 줄 시작을 넘지 않게
    for a, b in zip(cues, cues[1:]):
        if b.start <= a.start:
            b.start = a.start + 1.0
        a.end = min(a.end, b.start)

    # 줄 중간에 간주(INTERLUDE 초 넘게 쉼)가 끼어 있으면,
    # 간주 앞부분이 짧을 땐 줄을 간주 뒤로 옮기고, 길 땐 간주 시작에서 가사를 내린다.
    def sung(a: float, b: float) -> float:
        return sum(max(0.0, min(b, r1) - max(a, r0)) for r0, r1 in regions)

    for cue in cues:
        changed = True
        while changed:  # 한 줄에 간주가 여러 번 끼어 있을 수 있다
            changed = False
            for (_, b1), (a2, _) in zip(regions, regions[1:]):
                if cue.start < b1 and a2 < cue.end and a2 - b1 > INTERLUDE:
                    before, after = sung(cue.start, b1), sung(a2, cue.end)
                    if before < after:
                        cue.start = a2
                    else:
                        cue.end = b1 + 0.5
                    changed = True
                    break
    return cues


def vocals_timing(song: Song):
    path = find_vocals(song) or separate_vocals(song)
    print(f"[정렬] 목소리 트랙으로 노래 구간을 찾습니다: {path.name}")
    regions = sung_regions(path)
    if not regions:
        raise SystemExit("목소리 트랙에서 노래하는 구간을 찾지 못했습니다. --align even 으로 해 보세요.")
    print(f"[정렬] 노래 구간 {len(regions)}개, 첫 소리 {regions[0][0]:.1f}초, 마지막 소리 {regions[-1][1]:.1f}초")
    return place_lyrics(song.lyrics, regions)
