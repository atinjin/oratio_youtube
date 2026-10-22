"""가사에 맞춰 배경 장면을 정하고(scenes.yaml), 장면 그림을 만든다.

scenes.yaml 예시 (자동으로 만들어지고, 사람이 고칠 수 있다):

    - start: 0.0           # 이 시각부터 이 장면 (앞뒤 1초씩 서서히 바뀜)
      kind: pasture        # 장면 종류 (아래 SCENE_WORDS 참고)
      lines: 하느님은 나의 목자 ...    # 참고용: 이 장면 동안의 가사 첫 줄
      prompt: A lone shepherd ...      # AI 이미지 생성에 쓰는 영어 설명 (고치면 새로 생성)
    - start: 71.2
      kind: water
      image: my_lake.jpg   # (선택) 직접 고른 사진을 쓰려면 곡 폴더 기준 경로를 적는다
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from . import imagegen
from .painter import KINDS, paint
from .song import Song
from .timing import Cue

# 가사 낱말 → 장면. 위에 있을수록 먼저 고른다.
SCENE_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("valley", ("사망", "어두운", "골짜기", "두려", "원수", "환난", "고난", "눈물", "죽음")),
    ("presence", ("함께", "안위", "위로", "지팡이", "막대", "품")),
    ("house", ("집", "거하", "성전", "궁정", "영원히")),
    ("water", ("물가", "시냇", "강물", "강가", "바다", "샘", "생수")),
    ("sunrise", ("영혼", "살리", "소생", "바른 길", "길로", "인도", "아침", "새벽", "빛")),
    ("glory", ("아멘", "알렐루야", "영광", "찬양", "찬미", "선하심", "인자", "은혜", "자비", "사랑")),
    ("pasture", ("목자", "풀밭", "초장", "양 떼", "양떼", "들판", "푸른")),
    ("sky", ("하늘", "구름", "바람", "별")),
]

MIN_SCENE_SECONDS = 8.0   # 이보다 짧은 장면은 앞 장면에 합친다
FADE_SECONDS = 2.0        # 장면이 바뀌는 데 걸리는 시간


@dataclass
class Scene:
    start: float
    kind: str
    lines: str = ""
    image: str | None = None
    prompt: str = ""

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = imagegen.PROMPTS.get(self.kind, imagegen.PROMPTS["sky"])


def kind_for(line: str) -> str | None:
    for kind, words in SCENE_WORDS:
        if any(w in line for w in words):
            return kind
    return None


def plan_scenes(cues: list[Cue]) -> list[Scene]:
    """가사 줄마다 장면을 고르고, 같은 장면이 이어지는 줄들을 하나로 묶는다."""
    scenes: list[Scene] = []
    current = None
    for cue in cues:
        kind = kind_for(cue.text) or current or "pasture"
        if kind != current:
            # 가사가 나올 때 배경 전환이 끝나 있도록 조금 먼저 바꾼다
            scenes.append(Scene(max(cue.start - FADE_SECONDS / 2, 0.0), kind, cue.text.replace(" / ", " ")))
            current = kind
    if not scenes:
        return [Scene(0.0, "sky")]

    # 너무 짧은 장면은 앞 장면에 합친다
    merged: list[Scene] = [scenes[0]]
    for i, sc in enumerate(scenes[1:], 1):
        nxt = scenes[i + 1].start if i + 1 < len(scenes) else None
        if nxt is not None and nxt - sc.start < MIN_SCENE_SECONDS:
            continue
        if sc.kind == merged[-1].kind:
            continue
        merged.append(sc)
    merged[0].start = 0.0  # 첫 장면은 영상 처음(전주)부터
    return merged


def write_scenes(path: Path, scenes: list[Scene]) -> None:
    data = []
    for sc in scenes:
        item = {"start": round(sc.start, 2), "kind": sc.kind, "lines": sc.lines, "prompt": sc.prompt}
        if sc.image:
            item["image"] = sc.image
        data.append(item)
    header = (
        "# 배경 장면 계획입니다. 고친 뒤 다시 render 하면 반영됩니다.\n"
        f"# kind: {', '.join(KINDS)}\n"
        "# prompt: AI 이미지 생성에 쓰는 장면 설명(영어). 고치면 그 장면만 새로 생성합니다.\n"
        "# image: 직접 고른 사진을 쓰려면 곡 폴더 기준 파일 이름을 적습니다. (예: image: lake.jpg)\n"
    )
    path.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def read_scenes(path: Path) -> list[Scene]:
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or []
    scenes = [Scene(float(d["start"]), str(d.get("kind", "sky")), str(d.get("lines", "")), d.get("image"),
                    str(d.get("prompt") or "")) for d in data]
    scenes.sort(key=lambda s: s.start)
    if scenes:
        scenes[0].start = 0.0
    return scenes


def get_scenes(song: Song, cues: list[Cue], replan: bool) -> list[Scene]:
    path = song.folder / "scenes.yaml"
    if path.exists() and not replan:
        print(f"[배경] 저장된 장면 계획을 사용합니다: {path.name} (새로 만들려면 --replan)")
        return read_scenes(path)
    scenes = plan_scenes(cues)
    write_scenes(path, scenes)
    print(f"[배경] 가사에 맞춰 장면 {len(scenes)}개를 정했습니다: {path.name}")
    for sc in scenes:
        print(f"        {sc.start:6.1f}초  {sc.kind:9s} {sc.lines}")
    return scenes


def scene_images(song: Song, scenes: list[Scene], width: int, height: int, source: str = "auto") -> list[Path]:
    """장면마다 쓸 그림 파일 경로.

    source: auto  = AI 키가 있으면 AI 생성, 없으면 코드로 그린 그림
            ai    = AI 생성 (키가 없으면 멈춤)
            paint = 코드로 그린 그림
    직접 고른 사진(image:)이 있으면 언제나 그 사진을 쓴다.
    """
    out_dir = song.build_dir / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)

    provider = imagegen.detect_provider() if source in ("auto", "ai") else None
    if source == "ai" and provider is None:
        raise SystemExit(
            "AI 이미지 생성용 API 키가 없습니다. 하나를 환경 변수로 넣어 주세요.\n"
            "  OPENROUTER_API_KEY  (https://openrouter.ai/keys)\n"
            "  GEMINI_API_KEY  (Google AI Studio: https://aistudio.google.com/apikey)\n"
            "  OPENAI_API_KEY  (https://platform.openai.com/api-keys)"
        )
    if source == "auto" and provider is None and not all(sc.image for sc in scenes):
        print("[배경] AI API 키가 없어 코드로 그린 그림을 씁니다. (실사 이미지는 README 의 'AI 배경' 참고)")

    paths = []
    for i, sc in enumerate(scenes):
        if sc.image:
            p = (song.folder / sc.image).resolve()
            if not p.exists():
                raise SystemExit(f"scenes.yaml 의 사진을 찾을 수 없습니다: {p}")
            paths.append(p)
            continue
        if provider:
            try:
                paths.append(imagegen.generate(sc.prompt, out_dir, provider))
                continue
            except imagegen.ImageGenError as e:
                if source == "ai":
                    raise SystemExit(f"AI 이미지 생성에 실패했습니다: {e}")
                print(f"[경고] {i + 1}번 장면 AI 생성 실패, 그린 그림으로 대신합니다: {e}")
        # 움직임(천천히 이동)을 위해 10% 크게 그린다
        w, h = int(width * 1.1) // 2 * 2, int(height * 1.1) // 2 * 2
        p = out_dir / f"{i:02d}_{sc.kind}_{w}x{h}.png"
        if not p.exists():
            paint(sc.kind, w, h, seed=i).save(p)
        paths.append(p)
    return paths
