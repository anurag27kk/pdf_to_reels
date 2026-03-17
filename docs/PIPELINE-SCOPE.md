# Video Generation Pipeline — Scope

## What exists today

A working 4-step pipeline that takes a pharma PDF and produces an MP4 video reel:

```
step1_extract.py           PDF → text                              (pdftotext)
step2_generate_script.py   text + role + topic → script.json       (Claude API)
step3_generate_frames.py   script.json → per-scene PNGs            (Gemini image gen)
step3b_generate_voiceover.py  script.json → voiceover MP3          (Gemini TTS)
step4_stitch_video.py      frames + audio + logo + music → MP4     (FFmpeg)
```

### APIs used
- **Claude API** — script generation (step 2)
- **Google Gemini API** — image generation via `gemini-3.1-flash-image-preview` (step 3) AND TTS via `gemini-2.5-flash-preview-tts` (step 3b). Single API key.

### What's been generated (AllerDuo doctor intro)
- 12 scene images (content, quiz, quiz_answer, score, CTA, leaderboard)
- 12 per-scene audio MP3s
- Audio-synced durations JSON (actual audio length per scene)
- SRT subtitles from narration text
- 4 video iterations (v1 through v4)
- Hindi script + Hindi voiceover
- Background music + logo watermark

### Current problems
1. **No per-scene retry** — if scene 5's image fails, you re-run all 12 scenes
2. **Audio is one big MP3 in step3b** — but per-scene MP3s also exist in `_audio/` folder (unclear which path is current)
3. **Content scenes hardcoded to scene numbers** — step3 maps scene 1→intro, 2→composition, 3→mechanism, 4→indication by scene number, not by content
4. **Not generalized** — content prompt templates in step3 are AllerDuo-shaped (expects exactly 2 ingredients, nose+lungs icons)
5. **Subtitles disabled** — comment in step4 says "they didn't land well"
6. **No manifest tracking** — success/failure is determined by checking if files exist on disk

---

## Goal

A modular, generalized pipeline where:
1. **Phase 1** generates the full scene plan (script)
2. **Phase 2** generates per-scene assets (images + audio) in parallel, each independently retryable
3. **Phase 3** stitches everything together once all assets are ready
4. Works with any PDF + any role. No product-specific templates.

---

## Architecture: 3 phases

```
PHASE 1: PLAN (sequential, once)
    ┌─────────────┐     ┌──────────────────┐
    │ Extract PDF  │────▶│ Generate Script   │
    │ (pdftotext)  │     │ (Claude API)      │
    └─────────────┘     └──────────────────┘
                              │
                              ▼
                        script.json
                        (all scenes with visual_prompt + narration)

PHASE 2: GENERATE (parallel, per-scene, retryable)
    For each scene, independently:
    ┌──────────────────┐  ┌──────────────────┐
    │ Generate Image   │  │ Generate Audio    │
    │ (Gemini image)   │  │ (Gemini TTS)      │
    └──────────────────┘  └──────────────────┘
           │                       │
           ▼                       ▼
     scene_XX/image.png    scene_XX/audio.mp3

PHASE 3: ASSEMBLE (sequential, once all scenes ready)
    ┌──────────────────────────────────────┐
    │ Stitch frames + audio + logo + music │
    │ + subtitles → final MP4              │
    │ (FFmpeg)                             │
    └──────────────────────────────────────┘
```

---

## Output structure

```
output/{product}_{role}/
    manifest.json
    extracted.txt
    script.json
    scenes/
        scene_01/
            image.png
            audio.mp3
        scene_02/
            image.png
            audio.mp3
        ...
    video.mp4
```

---

## Module breakdown

```
generate.py                ← CLI entry point, runs phases
modules/
    manifest.py            ← create/read/update manifest.json
    extract.py             ← PDF → text (wraps pdftotext)
    script.py              ← text + role → script.json (Claude API)
    image.py               ← visual_prompt → image.png (Gemini image API)
    audio.py               ← narration text → audio.mp3 (Gemini TTS API)
    stitch.py              ← images + audio + logo + music → video.mp4 (FFmpeg)
    styles.py              ← role-based style configs (doctor, field)
```

Each module:
- Does one thing
- Takes explicit inputs, returns output path or error
- Can be run standalone for debugging: `python -m modules.image "prompt" out.png`
- Has no dependency on other modules (except manifest)

---

## Phase 1: Plan (detailed)

### extract.py
- Same as current `step1_extract.py`
- Skip if `extracted.txt` already exists

### script.py
- Same Claude API call as current `step2_generate_script.py`
- Key change: Claude generates a `visual_prompt` per scene — a complete, ready-to-use Gemini image prompt, not just a `visual_description`
- The role's style (from `styles.py`) is injected into Claude's system prompt so Claude writes visual_prompts in the right style
- Claude decides scene count and types based on the PDF content — no hardcoded "scene 1 = intro, scene 2 = composition"

Script JSON per scene:
```json
{
  "scene_number": 1,
  "scene_type": "content",
  "narration": "AllerDuo combines two active ingredients...",
  "visual_prompt": "Generate an image in 9:16 portrait format. Background: vivid blue gradient... Center: a photorealistic 3D white oval tablet... Above in bold white text: 'AllerDuo'...",
  "on_screen_text": ["AllerDuo", "Bilastine 20mg + Montelukast 10mg"],
  "transition": "fade"
}
```

The `visual_prompt` is the full Gemini prompt — `image.py` passes it directly to Gemini without modification. This is what makes the pipeline generalized: Claude tailors the prompt to whatever product is in the PDF.

After script generation, `manifest.json` is created with every scene marked `pending` for image and audio.

---

## Phase 2: Generate (detailed)

All scene tasks are independent. Run in parallel with `concurrent.futures.ThreadPoolExecutor`.

### image.py
- Input: `visual_prompt` string from script
- Output: `scenes/scene_XX/image.png`
- Uses `gemini-3.1-flash-image-preview`, 9:16 aspect ratio
- Validation: response must contain `inline_data`. If Gemini returns text only → mark `failed`
- On success → update manifest to `done`
- On failure → log error in manifest, continue to next scene

### audio.py
- Input: `narration` string from script
- Output: `scenes/scene_XX/audio.mp3`
- Uses `gemini-2.5-flash-preview-tts`
- Wraps narration in a style prompt ("Read in a clear, professional tone...")
- Outputs PCM → WAV → MP3 (same as current step3b)
- Validation: MP3 file > 0 bytes
- Also records actual audio duration in manifest (needed for stitch)

### Parallel execution
```
scene_01: image ─┐    audio ─┐
scene_02: image ─┤    audio ─┤
scene_03: image ─┤    audio ─┤   all running in parallel
scene_04: image ─┤    audio ─┤
scene_05: image ─┘    audio ─┘
```

If scene 3 image fails and scene 5 audio fails, everything else still completes. You retry only those 2.

---

## Phase 3: Assemble (detailed)

### stitch.py
- Only runs when manifest shows ALL scenes have `image: done` + `audio: done`
- Reads manifest for scene order, durations, transitions
- Same FFmpeg logic as current `step4_stitch_video.py`:
  - Frame images displayed for duration of their audio
  - Crossfade transitions between scenes
  - Logo watermark (optional)
  - Background music mixed in (optional)
  - Subtitles burned in (optional)
- Output: `video.mp4`

---

## Manifest

```json
{
  "job_id": "allerduo_doctor_20260306",
  "pdf": "AllerDuo.pdf",
  "role": "doctor",
  "product": "AllerDuo",
  "phase": "generate",
  "scenes": [
    { "scene": 1, "image": "done", "audio": "done", "audio_duration": 10.15 },
    { "scene": 2, "image": "failed", "image_error": "No image in response", "audio": "done", "audio_duration": 12.19 },
    { "scene": 3, "image": "done", "audio": "done", "audio_duration": 10.47 }
  ]
}
```

---

## Retry

```bash
# Retry all failed
python generate.py --retry output/allerduo_doctor/

# Retry specific scene + step
python generate.py --retry output/allerduo_doctor/ --scene 2 --step image
```

1. Reads manifest
2. Finds items with `failed` status (filtered by flags)
3. Re-runs only those
4. Updates manifest
5. If all now `done` → auto-runs Phase 3

---

## Generalizing: what changes from current code

| Current (hardcoded) | New (generalized) |
|---------------------|-------------------|
| `step3_generate_frames.py` has CONTENT_PROMPTS dict mapping scene numbers to prompt templates (scene 1→intro, 2→composition, etc.) | Claude generates `visual_prompt` per scene directly — no hardcoded templates in image.py |
| Scene type detection relies on `scene_type` field + scene number | Claude labels scene types; image.py just uses the `visual_prompt` as-is |
| Content prompts assume 2 ingredients, nose+lungs icons | Claude adapts to whatever product is in the PDF |
| Style 3 (blue professional) hardcoded in STYLE_BASE | Style comes from `styles.py` config, injected into Claude's prompt |
| `step3b_generate_voiceover.py` generates one big MP3 | `audio.py` generates per-scene MP3 (the `_audio/` folder approach) |

The key insight: **move prompt engineering from image.py into script.py**. Claude writes the Gemini prompts. Image.py becomes a dumb pipe — it takes a prompt, calls Gemini, saves the image. That's it.

---

## Build order

| # | What | Effort | Notes |
|---|------|--------|-------|
| 1 | `manifest.py` | Small | Create/read/update/query manifest |
| 2 | `styles.py` | Small | Doctor + field style configs |
| 3 | `extract.py` | Small | Refactor from step1 (basically copy) |
| 4 | `script.py` | Medium | Refactor step2 — add visual_prompt generation, style injection |
| 5 | `image.py` | Small | Simplify from step3 — just take prompt, call Gemini, save |
| 6 | `audio.py` | Small | Refactor from step3b — per-scene, same Gemini TTS |
| 7 | `generate.py` | Medium | CLI orchestrator — 3 phases, parallel execution, retry |
| 8 | `stitch.py` | Medium | Refactor from step4_stitch — read manifest for durations/paths |

Start with: **1 → 2 → 3 → 4 → 5** — that gets you to script + images working end-to-end. Then 6 → 8 → 7.

---

## Open decisions

1. **On-screen text** — bake into Gemini image (current approach, simpler) vs overlay in stitch step (needed for language switching)?
2. **Subtitles** — currently disabled ("didn't land well"). Revisit after modular pipeline is working?
