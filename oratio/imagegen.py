"""이미지 생성 AI 로 장면 배경(실사 영화 스틸컷 느낌)을 만든다.

지원하는 서비스 (환경 변수에 API 키를 넣어 두면 자동으로 고른다):
  - Google Gemini / Imagen :  GEMINI_API_KEY  (또는 GOOGLE_API_KEY)
  - OpenAI                 :  OPENAI_API_KEY

추가 패키지 없이 표준 라이브러리(urllib)로만 호출한다.
같은 프롬프트로 만든 이미지는 build/scenes/ 에 저장해 두고 다시 쓰므로, 두 번 돈이 들지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# 모든 장면 프롬프트 뒤에 붙는 공통 스타일
STYLE_SUFFIX = (
    "Cinematic film still, photorealistic, shot on 35mm anamorphic lens, natural light, "
    "shallow depth of field, rich but restrained color grading, epic biblical film atmosphere, "
    "Judean hills of ancient Israel, 16:9 widescreen. "
    "Leave the lower third of the frame calm and uncluttered for subtitles. "
    "No text, no letters, no watermark, no modern objects, no visible faces."
)

# 장면 종류별 기본 프롬프트 (시편 23편 + 일반 찬양 가사)
PROMPTS = {
    "pasture": "A lone shepherd seen from behind, holding a wooden staff, gently leading a flock of sheep "
               "across lush green pastures on rolling hills at golden hour, warm sunlight and soft haze.",
    "water": "Still, quiet waters of a calm stream winding through a peaceful valley at dawn, thin mist "
             "on the surface, a few sheep resting by the bank, soft reflections of the morning sky.",
    "sunrise": "A narrow ancient path winding through hills toward the rising sun, golden rays breaking "
               "over the ridge, dew on the grass, a sense of renewal and guidance.",
    "valley": "A deep, dark rocky ravine in the Judean wilderness at night, steep cliffs, cold moonlight, "
              "drifting fog, a small warm lantern light carried along the narrow path far below.",
    "presence": "Heavenly god rays breaking through dark storm clouds into a deep valley, a shepherd's rod "
                "and staff silhouetted on a rock, light overcoming the darkness, comfort and protection.",
    "glory": "Radiant golden light pouring over vast hills and a valley at sunrise, glowing clouds, "
             "majestic and peaceful, a feeling of goodness and mercy filling the land.",
    "house": "An ancient stone church on a quiet hill at blue hour, warm candlelight glowing from its "
             "windows and open door, a clear sky full of stars above, eternal and welcoming.",
    "sky": "Vast open sky with soft clouds lit by the morning sun over quiet hills, serene and hopeful.",
}


class ImageGenError(RuntimeError):
    pass


def detect_provider() -> str | None:
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return None


def full_prompt(prompt: str) -> str:
    return f"{prompt.strip()} {STYLE_SUFFIX}"


def _post(url: str, body: dict, headers: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise ImageGenError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise ImageGenError(f"접속 실패: {e.reason}") from e


def _gemini(prompt: str) -> bytes:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    model = os.environ.get("ORATIO_IMAGE_MODEL", "imagen-4.0-generate-001")
    headers = {"x-goog-api-key": key}

    if model.startswith("imagen"):
        data = _post(f"{base}/{model}:predict",
                     {"instances": [{"prompt": prompt}],
                      "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}}, headers)
        preds = data.get("predictions") or []
        if not preds or "bytesBase64Encoded" not in preds[0]:
            raise ImageGenError(f"이미지가 오지 않았습니다 (안전 필터에 걸렸을 수 있음): {str(data)[:300]}")
        return base64.b64decode(preds[0]["bytesBase64Encoded"])

    # gemini-2.5-flash-image 같은 Gemini 이미지 모델
    data = _post(f"{base}/{model}:generateContent",
                 {"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseModalities": ["IMAGE"],
                                       "imageConfig": {"aspectRatio": "16:9"}}}, headers)
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise ImageGenError(f"이미지가 오지 않았습니다: {str(data)[:300]}")


def _openai(prompt: str) -> bytes:
    key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("ORATIO_IMAGE_MODEL", "gpt-image-1")
    data = _post("https://api.openai.com/v1/images/generations",
                 {"model": model, "prompt": prompt, "size": "1536x1024", "quality": "high", "n": 1},
                 {"Authorization": f"Bearer {key}"})
    try:
        return base64.b64decode(data["data"][0]["b64_json"])
    except (KeyError, IndexError) as e:
        raise ImageGenError(f"이미지가 오지 않았습니다: {str(data)[:300]}") from e


def generate(prompt: str, out_dir: Path, provider: str) -> Path:
    """프롬프트로 이미지를 만들어 저장한다. 같은 프롬프트는 저장된 파일을 그대로 쓴다."""
    text = full_prompt(prompt)
    model = os.environ.get("ORATIO_IMAGE_MODEL", "")
    digest = hashlib.sha1(f"{provider}|{model}|{text}".encode()).hexdigest()[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in (".png", ".jpg"):
        cached = out_dir / f"ai_{digest}{ext}"
        if cached.exists():
            return cached

    print(f"[배경] AI 이미지 생성 중 ({provider}): {prompt[:60]}...")
    raw = _gemini(text) if provider == "gemini" else _openai(text)
    ext = ".jpg" if raw[:3] == b"\xff\xd8\xff" else ".png"
    path = out_dir / f"ai_{digest}{ext}"
    path.write_bytes(raw)
    return path
