# Duolingo for Pharma

Converts pharmaceutical PDF monographs into short (60-120s) educational video reels with quizzes, gamification, and Indian English voiceover. Built for JagsonPal Pharma L&D.

## Quick Start

### Prerequisites

```bash
brew install poppler ffmpeg
```

### Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIzaSy...
ELEVENLABS_API_KEY=sk_...
```

### Run (Agent — recommended)

```bash
# Single reel
python video_agent.py "pdfs/AllerDuo.pdf" --topic intro

# All topics for a drug
python video_agent.py "pdfs/AllerDuo.pdf" --all-topics

# Production mode (skip quiz/gamification for faster output)
python video_agent.py "pdfs/AllerDuo.pdf" --topic intro --mode production

# Specific profile + topic
python video_agent.py "pdfs/Tibrolin_Trypsin + Bromelain + Rutoxide.pdf" --profile doctor --topic mechanism

# Gemini TTS instead of ElevenLabs
python video_agent.py "pdfs/AllerDuo.pdf" --tts gemini --voice kore

# Interactive mode (agent asks what to do)
python video_agent.py
```

**Agent flags:**

| Flag | Default | Options |
|------|---------|---------|
| `--profile` | `all` | `doctor`, `stockist`, `retailer`, `all` |
| `--topic` | (agent picks) | `intro`, `indications`, `mechanism`, `dosage_safety`, `interactions`, `side_effects` |
| `--all-topics` | off | Generate all viable topics |
| `--tts` | `elevenlabs` | `elevenlabs`, `gemini` |
| `--voice` | `gaurav` | ElevenLabs: gaurav/raj/viraj/ruhaan/jeevan. Gemini: kore/charon/puck/aoede |
| `--mode` | `demo` | `demo` (full with quiz), `production` (content only, faster) |
| `--max-turns` | 50 | Agent turn budget |

### Run (Pipeline — no agent)

```bash
# Single reel
python run_pipeline.py "pdfs/AllerDuo.pdf" all intro

# All topics
python run_pipeline.py "pdfs/AllerDuo.pdf" all --all-topics

# Production mode
python run_pipeline.py "pdfs/AllerDuo.pdf" doctor intro --mode production
```

## What It Produces

Each video reel (demo mode) has 3 parts:

1. **Educational content** (4-5 scenes) — AI-generated 3D photorealistic frames with voiceover
2. **Quiz** (2 MCQs) — clinically relevant questions with plausible distractors
3. **Gamification** — score celebration, streak CTA, leaderboard

**Output**: MP4, 9:16 portrait, 1080x1920, ~5-8 MB, with phrase-based subtitles and logo overlays.

Production mode skips quiz and gamification — content scenes only.

### Demo Videos

Pre-generated samples in `demos/`:

| File | Drug | Topic | Subtitles |
|------|------|-------|-----------|
| `AllerDuo_intro.mp4` | AllerDuo (Bilastine + Montelukast) | Intro | Yes |
| `AllerDuo_mechanism.mp4` | AllerDuo | Mechanism | Yes |
| `AllerDuo_dosage_safety.mp4` | AllerDuo | Dosage & Safety | Yes |
| `Tibrolin_intro.mp4` | Tibrolin (Trypsin + Bromelain + Rutoside) | Intro | No |
| `Subneuro-NT_intro.mp4` | Subneuro-NT (Nortriptyline + Pregabalin + Methylcobalamin) | Intro | No |
| `Rexulti_intro.mp4` | Rexulti (Brexpiprazole) | Intro | No |

### Tested Drugs

| Drug | Composition | Area |
|------|------------|------|
| AllerDuo | Bilastine 20mg + Montelukast 10mg | Allergic rhinitis |
| Tibrolin | Trypsin + Bromelain + Rutoside | Anti-inflammatory enzyme |
| Subneuro-NT | Nortriptyline + Pregabalin + Methylcobalamin | Neuropathic pain |
| Rexulti | Brexpiprazole | Atypical antipsychotic |

## Pipeline Architecture

```
Drug PDF
  │
  ├─ Step 1: pdftotext ──────────→ extracted text (.md/.txt)
  ├─ Step 1b: Claude analyze ────→ topic viability analysis (.json)
  ├─ Step 2: Claude script gen ──→ structured script (.json)
  │
  ├─ Step 3a: Gemini Flash ──────→ AI frames (.png)  ─┐
  │   (+ Pillow fallback)                              ├─ parallel
  ├─ Step 3b: ElevenLabs TTS ───→ voiceover (.mp3)   ─┘
  │                                + per-scene durations
  │
  ├─ Step 4: FFmpeg stitch ─────→ raw video (.mp4)
  └─ Step 5: Pillow + FFmpeg ───→ final video with subtitles (.mp4)
```

## Configuration

All prompts and model settings in `config/` — editable without touching Python:

```
config/
├── models.json           # Model IDs, voice settings, video codec params
└── prompts/
    ├── agent_system.txt  # Agent decision rules
    ├── script_system.txt # Script generation rules
    ├── script_user.txt   # Script JSON schema
    ├── analyze_*.txt     # Content analysis prompts
    ├── validate_*.txt    # Factual validation prompts
    ├── frame_style.txt   # Visual style (3D photorealistic)
    ├── frame_text_guard.txt # Text minimization for AI images
    ├── profiles.json     # Audience profiles
    ├── topics.json       # Topic templates with durations
    └── tts_gemini.txt    # Gemini TTS voice instructions
```

## File Reference

| File | Purpose |
|------|---------|
| `video_agent.py` | Autonomous agent — raw Anthropic tool_use loop, 16 tools, adaptive self-correction |
| `run_pipeline.py` | Sequential pipeline runner (no agent, no self-correction) |
| `generate_series.py` | Batch generation across multiple drugs |
| `step1_extract.py` | PDF text extraction (pdftotext / PyMuPDF / OCR fallback) |
| `step1b_analyze_content.py` | Content analysis and topic identification |
| `step2_generate_script.py` | Script generation with Claude |
| `step3_generate_frames.py` | Frame generation (Gemini Flash Image Preview + Pillow fallback) |
| `step3_generate_voiceover.py` | ElevenLabs voiceover (per-scene, Indian English) |
| `step3b_generate_voiceover.py` | Gemini TTS voiceover (alternative) |
| `step4_stitch_video.py` | FFmpeg video stitching (concat, logo, bg music) |
| `burn_subtitles.py` | Subtitle burning (Pillow overlay + FFmpeg composite) |
| `validate_script.py` | Script factual accuracy validation |
| `config_loader.py` | Loads config from `config/` |
| `frame_templates.py` | Pillow renderers for quiz/score/CTA/leaderboard frames |

## Costs & Timing

**Per video (~8-12 min generation time):**

| Service | Cost |
|---------|------|
| Claude (script + validation + analysis) | ~$0.02-0.05 |
| Gemini Flash (12-13 frames) | ~$0.01 |
| ElevenLabs (2-3 min audio) | ~$0.05-0.10 |
| Agent overhead (if using video_agent.py) | ~$0.10-0.30 |
| **Total** | **~$0.15-0.45** |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Missing env vars" | Create `.env` in project root with all 3 API keys |
| Frames look flat/cartoonish | Check `config/prompts/frame_style.txt` |
| Audio drifts out of sync | Verify `crossfade_duration` is `0.0` in `config/models.json` |
| ElevenLabs rate limited | Free tier gets blocked — need paid plan |
| Script validation < 0.8 | Agent auto-rewrites. Manual: re-run step 2 with stricter source text |
| `output/` empty after run | Normal — `output/` is gitignored. Demo samples are in `demos/` |
