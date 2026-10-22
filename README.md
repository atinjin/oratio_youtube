# Oratio YouTube — 성가대 특송 뮤직비디오 자동 만들기

특송 음원과 가사만 넣으면 **제목 화면 → 가사 자막 → 성경 구절·크레딧 화면**이 들어간
유튜브용 MP4 영상을 만들어 주는 도구입니다. 내 PC(Windows / macOS / Linux)에서 돌아갑니다.

```
songs/2026-10-25_주님의은혜/
├── audio.mp3          ← 특송 음원 (필수)
├── lyrics.txt         ← 가사 (필수)
├── meta.yaml          ← 제목, 성가대, 크레딧, 성경 구절
├── background.jpg     ← 배경 사진 또는 background.mp4 (선택, 없으면 기본 그라데이션)
│
├── timing.lrc         → 자동으로 만들어지는 가사 타이밍 (고칠 수 있음)
├── 2026-10-25_주님의은혜.mp4   → 완성 영상
├── thumbnail.jpg      → 썸네일
└── description.txt    → 유튜브 설명란에 붙여 넣을 글 (가사 포함)
```

## 1. 처음 한 번만 설치

1. **Python 3.10 이상**
   - Windows: <https://www.python.org/downloads/> 에서 설치할 때 *Add python.exe to PATH* 를 체크합니다.
2. **FFmpeg**
   - Windows: 터미널(PowerShell)에서 `winget install Gyan.FFmpeg` 를 실행한 뒤 터미널을 새로 엽니다.
   - macOS: `brew install ffmpeg`
3. 이 폴더에서 필요한 패키지와 기본 폰트를 받습니다.

```bash
pip install -r requirements.txt
python -m oratio fonts        # 나눔명조 폰트를 fonts/ 폴더에 받습니다
```

> Windows 에서 `python` 이 안 되면 `py` 로 바꿔서 실행해 보세요. (예: `py -m oratio fonts`)

## 2. 곡마다 하는 일

```bash
# ① 곡 폴더 틀 만들기
python -m oratio new songs/2026-10-25_주님의은혜

# ② 폴더에 audio.mp3 를 넣고, meta.yaml 과 lyrics.txt 를 고칩니다.
#    배경 사진을 쓰려면 background.jpg 도 넣습니다.

# ③ 앞부분 30초만 빠르게 미리보기
python -m oratio render songs/2026-10-25_주님의은혜 --preview 30

# ④ 가사 타이밍이 어긋났다면 timing.lrc 를 메모장으로 고친 뒤 다시 ③

# ⑤ 최종 영상 만들기
python -m oratio render songs/2026-10-25_주님의은혜
```

### 가사 쓰는 법 (`lyrics.txt`)

- **한 줄 = 화면에 한 번에 보이는 가사**입니다.
- 화면 안에서 두 줄로 보여주려면 ` / ` 로 나눕니다. 예: `어둔 밤 지나 / 새 아침 밝아 오니`
- 빈 줄과 `#` 으로 시작하는 줄은 무시됩니다. (1절, 2절 구분 메모 등에 쓰시면 됩니다)
- 후렴을 반복해서 부르면 반복한 만큼 가사를 다시 적어 주세요.

### 가사 타이밍 고치는 법 (`timing.lrc`)

처음 render 하면 가사 타이밍이 `timing.lrc` 에 저장되고, 다음부터는 이 파일을 그대로 씁니다.

```
[00:12.50]주님의 은혜 강물같이
[00:17.20]내 영혼 깊이 흘러 넘치네
[00:41.00]                      ← 내용 없는 줄 = 이 시각에 가사를 내림 (간주)
```

- `[분:초]` 를 고치고 다시 render 하면 반영됩니다.
- 가사를 많이 바꿨거나 처음부터 다시 맞추고 싶으면 `--retime` 을 붙입니다.

## 3. 가사 자동 맞추기 (선택)

기본 상태에서는 가사를 글자 수에 비례해 **균등하게** 나눕니다. 실제 노래와는 어긋나기 쉬워서
`timing.lrc` 를 손봐야 합니다. 아래 두 방법 중 하나를 설치하면 훨씬 덜 어긋납니다.

### 방법 A. 목소리 구간 맞춤 — 합창에 추천

반주를 걷어내고 목소리만 남긴 뒤, **노래하는 구간에만** 가사를 나눠 놓습니다.
간주 동안에는 가사를 내리고, 줄의 시작을 노래가 새로 시작하는 지점에 맞춥니다.
합창은 음성 인식이 가사를 잘 알아듣지 못해서 이 방법이 더 안정적입니다.

```bash
pip install -r requirements-vocals.txt      # PyTorch 없이 CPU 로 동작
python -m oratio render songs/곡폴더 --align vocals --retime --timing-only
```

- 처음 실행할 때 분리 모델(약 65MB)을 `models/` 폴더에 받습니다. 5분 곡 기준으로 분리에 3~5분 걸립니다.
- 분리한 목소리는 `build/vocals.wav` 에 저장되어, 다음부터는 바로 씁니다.
- 다른 프로그램(UVR 등)으로 분리한 목소리 파일이 있으면 곡 폴더에 `vocals.wav` 로 넣어도 됩니다.
- 가사 줄 단위로 "어느 구간쯤"을 잡아 주는 방식이라 1~2초 어긋날 수 있습니다. 미리보기로 확인하고 `timing.lrc` 를 조금 고쳐 주세요.

### 방법 B. Whisper 정렬

**Whisper**(음성 인식 AI)를 설치하면, 이미 있는 가사를 음원에 맞춰 **자동으로 정렬**합니다.
독창이나 가사가 또렷한 녹음에 잘 맞습니다.

```bash
pip install -r requirements-whisper.txt
python -m oratio render songs/곡폴더 --retime --timing-only    # 타이밍만 먼저 만들어 확인
```

| 옵션 | 설명 |
|---|---|
| `--model small` | 빠르지만 덜 정확합니다. 기본값은 `medium`, 가장 정확한 것은 `large-v3` |
| `--vocals` | 반주를 걷어내고 목소리로만 정렬합니다. 합창은 더 정확해지지만 느립니다. (`demucs` 설치 필요) |

- NVIDIA 그래픽카드가 있으면 훨씬 빠릅니다. 없으면 CPU 로 돌아가며, 5분 곡에 수 분~수십 분 걸릴 수 있습니다.
- 합창은 발음이 뭉개져서 일부 줄이 어긋날 수 있습니다. 미리보기로 확인하고 `timing.lrc` 를 조금 고치는 흐름을 권장합니다.

## 4. 그 밖의 옵션

```bash
python -m oratio render songs/곡폴더 --vertical                  # 세로 영상 (유튜브 쇼츠용)
python -m oratio render songs/곡폴더 --preview 20 --start 60     # 1분 지점부터 20초 미리보기
python -m oratio render songs/곡폴더 --align even --retime        # 균등 분배로 다시
```

### 화면 스타일 바꾸기 (`style.yaml`, 선택)

곡 폴더에 `style.yaml` 을 두면 원하는 값만 바꿀 수 있습니다. 전체 항목은 `oratio/style.py` 에 있습니다.

```yaml
lyric_size: 80            # 가사 글자 크기
lyric_position: center    # bottom(아래) | center(가운데)
background_dim: 0.3       # 배경 어둡게 (0~1)
background_blur: 8        # 배경 흐리게 (0 = 끔)
background_motion: false  # 배경 사진 천천히 움직이기 끄기
font: NanumMyeongjo       # fonts/ 폴더에 넣은 다른 폰트 이름으로 바꿀 수 있음
```

> 다른 폰트를 쓰려면 `.ttf` 파일을 `fonts/` 폴더에 넣고 `font:` 에 글꼴 이름을 적습니다.
> 이름에 `[wght]` 가 붙은 **가변 폰트는 인식이 잘 안 되니**, 굵기별로 나뉜 일반 폰트 파일을 쓰는 게 좋습니다.

## 5. 가사에 맞춘 배경 (AI 실사 이미지)

`--scenes` 를 붙이면 가사 내용에 맞춰 장면을 나누고, 장면마다 다른 배경을 보여줍니다.
장면이 바뀔 때는 2초 동안 서서히 넘어갑니다.

```bash
python -m oratio render songs/곡폴더 --scenes
```

1. **장면 계획**: 가사 낱말로 장면을 고릅니다. (목자·풀밭 → 초원, 물가 → 잔잔한 물, 영혼·바른 길 → 해 뜨는 길,
   사망·어두운 → 어둠의 골짜기, 함께·안위 → 골짜기에 내리는 빛, 집 → 언덕 위 성당, 아멘·인자 → 영광의 빛)
   결과는 곡 폴더의 `scenes.yaml` 에 저장되고, 시각·장면·프롬프트를 고칠 수 있습니다. 새로 만들려면 `--replan`.
2. **이미지 생성**: 장면마다 영어 프롬프트(`prompt:`)로 **실사 영화 스틸컷 느낌**의 이미지를 AI 로 만듭니다.
   API 키를 환경 변수로 넣어 두면 자동으로 씁니다.

| 서비스 | 환경 변수 | 키 발급 |
|---|---|---|
| Google Gemini (Imagen 4) | `GEMINI_API_KEY` | <https://aistudio.google.com/apikey> |
| OpenAI (gpt-image-1) | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> |

```bash
# macOS / Linux
export GEMINI_API_KEY=발급받은키
# Windows PowerShell
$env:GEMINI_API_KEY="발급받은키"
```

- 이미지 생성은 **유료**입니다. 곡 하나에 장면 8~10장 정도이고, 한 번 만든 이미지는 `build/scenes/` 에 저장해서
  다시 render 해도 새로 만들지 않습니다. (`prompt:` 를 고친 장면만 새로 만듭니다)
- 모델을 바꾸려면 `ORATIO_IMAGE_MODEL` 환경 변수를 씁니다. (예: `gemini-2.5-flash-image`)
- 마음에 드는 사진이 따로 있으면 `scenes.yaml` 의 해당 장면에 `image: 사진.jpg` 를 적으면 그 사진을 씁니다.
- API 키가 없으면 코드로 그린 풍경화로 대신합니다. (`--image-source paint`)

## 6. 유튜브에 올릴 때

- 영상: `곡폴더/곡폴더이름.mp4`
- 설명란: `description.txt` 내용을 붙여 넣습니다.
- 썸네일: `thumbnail.jpg` (제목 화면에서 자동으로 캡처합니다)

## 주의할 점

- **저작권**: 찬양곡의 가사와 곡에는 저작권이 있는 경우가 많습니다. 교회의 저작권 라이선스(CCLI 등)나 출판사 허락 범위를 먼저 확인해 주세요.
- **초상권**: 성가대원 얼굴이 나오는 사진을 배경으로 쓸 때는 미리 동의를 받아 두는 게 좋습니다.
- 음원과 완성 영상은 용량이 커서 git 에 올라가지 않도록 `.gitignore` 에 넣어 두었습니다.

## 다음 단계 아이디어

- 가사 줄마다 스페이스바로 박자를 찍어 타이밍을 맞추는 간단한 웹 화면
- 인트로·아웃트로 애니메이션 템플릿 추가
- YouTube API 로 비공개 자동 업로드
