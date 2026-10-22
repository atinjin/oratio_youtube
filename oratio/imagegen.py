"""이미지 생성 AI 로 장면 배경(실사 영화 스틸컷 느낌)을 만든다.

지원하는 서비스 (환경 변수에 API 키를 넣어 두면 자동으로 고른다):
  - OpenRouter             :  OPENROUTER_API_KEY  (키 하나로 Gemini 등 여러 이미지 모델 사용)
  - Google Gemini / Imagen :  GEMINI_API_KEY  (또는 GOOGLE_API_KEY)
  - OpenAI                 :  OPENAI_API_KEY

모델을 바꾸려면 ORATIO_IMAGE_MODEL 환경 변수를 쓴다.
키를 환경 변수 대신 프록시가 넣어 주는 환경(Claude Code 클라우드의 Network secrets 등)에서는
ORATIO_IMAGE_PROVIDER=openrouter 처럼 서비스만 지정하면, 인증 헤더 없이 요청을 보낸다.

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
    "Full-bleed photograph that fills the entire frame edge to edge, with no borders, bands, "
    "letterboxing, panels or overlays. Keep the main subject in the upper two-thirds of the frame. "
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
    forced = os.environ.get("ORATIO_IMAGE_PROVIDER", "").strip().lower()
    if forced in ("openrouter", "gemini", "openai"):
        return forced
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
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
    headers = {"x-goog-api-key": key} if key else {}

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
    key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("ORATIO_IMAGE_MODEL", "gpt-image-1")
    data = _post("https://api.openai.com/v1/images/generations",
                 {"model": model, "prompt": prompt, "size": "1536x1024", "quality": "high", "n": 1},
                 {"Authorization": f"Bearer {key}"} if key else {})
    try:
        return base64.b64decode(data["data"][0]["b64_json"])
    except (KeyError, IndexError) as e:
        raise ImageGenError(f"이미지가 오지 않았습니다: {str(data)[:300]}") from e


def _openrouter(prompt: str) -> bytes:
    key = os.environ.get("OPENROUTER_API_KEY")
    model = os.environ.get("ORATIO_IMAGE_MODEL", "google/gemini-3-pro-image")
    auth = {"Authorization": f"Bearer {key}"} if key else {}  # 없으면 프록시가 넣어 준다
    data = _post("https://openrouter.ai/api/v1/chat/completions",
                 {"model": model,
                  "messages": [{"role": "user", "content": f"Generate an image: {prompt}"}],
                  "modalities": ["image", "text"],
                  "image_config": {"aspect_ratio": "16:9",
                                   **({"image_size": size} if (size := os.environ.get("ORATIO_IMAGE_SIZE", "2K")) else {})}},
                 {**auth,
                  "HTTP-Referer": "https://github.com/atinjin/oratio_youtube",
                  "X-Title": "oratio_youtube"})
    if "error" in data:
        raise ImageGenError(str(data["error"])[:300])
    for choice in data.get("choices", []):
        for img in choice.get("message", {}).get("images") or []:
            url = (img.get("image_url") or img.get("imageUrl") or {}).get("url", "")
            if url.startswith("data:"):
                return base64.b64decode(url.split(",", 1)[1])
            if url.startswith("http"):
                with urllib.request.urlopen(url, timeout=120) as resp:
                    return resp.read()
    raise ImageGenError(f"이미지가 오지 않았습니다 (이미지 생성 모델인지 확인해 주세요): {str(data)[:300]}")


def generate(prompt: str, out_dir: Path, provider: str) -> Path:
    """프롬프트로 이미지를 만들어 저장한다. 같은 프롬프트는 저장된 파일을 그대로 쓴다."""
    text = full_prompt(prompt)
    model = os.environ.get("ORATIO_IMAGE_MODEL", "")
    size = os.environ.get("ORATIO_IMAGE_SIZE", "2K") if provider == "openrouter" else ""
    digest = hashlib.sha1(f"{provider}|{model}|{size}|{text}".encode()).hexdigest()[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in (".png", ".jpg"):
        cached = out_dir / f"ai_{digest}{ext}"
        if cached.exists():
            return cached

    print(f"[배경] AI 이미지 생성 중 ({provider}): {prompt[:60]}...")
    raw = {"openrouter": _openrouter, "gemini": _gemini, "openai": _openai}[provider](text)
    ext = ".jpg" if raw[:3] == b"\xff\xd8\xff" else ".png"
    path = out_dir / f"ai_{digest}{ext}"
    path.write_bytes(raw)
    return path
