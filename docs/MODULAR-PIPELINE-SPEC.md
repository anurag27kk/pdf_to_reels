# Modular Video Pipeline — Buildable Spec

## What we're building

A modular pipeline that converts any PDF + role into a video. Each piece runs independently, outputs to its own file, and can be inspected/retried without touching anything else.

```
python generate.py "AllerDuo.pdf" doctor
```

---

## Directory structure

```
poc/
    generate.py              ← entry point
    modules/
        __init__.py
        manifest.py          ← state tracking
        extract.py           ← PDF → text
        script.py            ← text + role → script.json (Claude)
        image.py             ← prompt → image.png (Gemini)
        audio.py             ← narration → audio.mp3 (ElevenLabs)
        stitch.py            ← images + audio → video.mp4 (FFmpeg)
        styles.py            ← role-based style/prompt configs
```

All existing `step*.py` files stay untouched — this is a new system alongside them.

---

## Output structure

```
output/allerduo_doctor/
    manifest.json
    extracted.txt
    script.json
    scenes/
        scene_01/
            image.png
            audio.mp3          ← silence (0-byte or generated silence) for quiz/leaderboard scenes
        scene_02/
            image.png
            audio.mp3
        ...
    video.mp4
```

Each scene is a folder. You can:
- Open `scene_03/image.png` — does it look right?
- Play `scene_03/audio.mp3` — does the narration sound right?
- If bad → regenerate just that one: `python generate.py --retry --scene 3 --step image`

---

## Manifest (manifest.json)

Tracks what's done, what failed, and the data needed for stitching.

```json
{
  "job_id": "allerduo_doctor_20260306_143022",
  "pdf": "AllerDuo.pdf",
  "role": "doctor",
  "product": "AllerDuo",
  "created_at": "2026-03-06T14:30:22Z",
  "total_scenes": 12,
  "scenes": [
    {
      "scene": 1,
      "scene_type": "content",
      "image": "done",
      "audio": "done",
      "audio_duration": 10.15
    },
    {
      "scene": 2,
      "scene_type": "content",
      "image": "failed",
      "image_error": "No image in Gemini response (text only)",
      "image_retries": 1,
      "audio": "done",
      "audio_duration": 12.19
    },
    {
      "scene": 5,
      "scene_type": "quiz",
      "image": "done",
      "audio": "done",
      "audio_duration": 4.0,
      "audio_is_silence": true
    }
  ],
  "video": "pending"
}
```

---

## Module specs

### modules/manifest.py

```python
# Core functions:
def create(output_dir, pdf, role, product, scenes) -> dict
    # Creates manifest.json with all scenes set to "pending"

def load(output_dir) -> dict
    # Reads manifest.json from disk

def update_scene(output_dir, scene_num, step, status, **kwargs)
    # Update one scene's step: update_scene(dir, 3, "image", "done")
    # Or: update_scene(dir, 3, "image", "failed", error="No image in response")

def get_failed(output_dir, step=None, scene=None) -> list
    # Get all failed items, optionally filtered
    # get_failed(dir) → all failed
    # get_failed(dir, step="image") → all failed images
    # get_failed(dir, scene=3) → all failed items for scene 3

def all_scenes_ready(output_dir) -> bool
    # True if every scene has image=done and audio=done

def set_video_status(output_dir, status, **kwargs)
    # Mark video as done/failed
```

No classes. Just functions that read/write `manifest.json`. Simple.

---

### modules/extract.py

Wraps pdftotext. Same logic as current `step1_extract.py`.

```python
def extract(pdf_path, output_dir) -> str
    # Runs pdftotext, saves to output_dir/extracted.txt
    # Returns path to text file
    # Skips if file already exists
```

---

### modules/script.py

Claude API call. Refactored from `step2_generate_script.py`.

```python
def generate_script(text_path, role, output_dir) -> dict
    # Reads extracted text
    # Gets style config from styles.py for the role
    # Calls Claude API with:
    #   - System prompt: pharma video script writer + style guide
    #   - User prompt: PDF text + role context + output format spec
    # Saves to output_dir/script.json
    # Returns parsed script dict
```

**Key change from current step2**: Claude now generates a `visual_prompt` per scene — a complete Gemini-ready image prompt. This replaces the hardcoded prompt templates in `step3_generate_frames.py`.

Claude's output format per scene:
```json
{
  "scene_number": 1,
  "scene_type": "content",
  "duration_seconds": 15,
  "narration": "Meet AllerDuo - a dual-action...",
  "visual_prompt": "Generate an image in 9:16 portrait format. Background: vivid blue gradient from royal blue to sky blue. Center: a photorealistic 3D white oval tablet floating with soft shadow. Above in bold white text: 'AllerDuo'. Below: 'Bilastine 20mg + Montelukast 10mg'. Bottom: orange rounded banner 'Film-Coated Tablets'. Do NOT include phones, devices, or watermarks.",
  "on_screen_text": ["AllerDuo", "Bilastine 20mg + Montelukast 10mg"],
  "transition": "fade"
}
```

Claude also generates quiz scenes, score, CTA, leaderboard — same scene types as current. The `visual_prompt` for a quiz scene describes the quiz card layout, options, etc.

The style guide (from `styles.py`) is injected into the system prompt so Claude writes visual_prompts that match the role's look.

---

### modules/image.py

Gemini image generation. Simplified from `step3_generate_frames.py`.

```python
def generate_image(visual_prompt, output_path) -> bool
    # Calls Gemini (gemini-3.1-flash-image-preview) with the prompt
    # Saves image to output_path
    # Returns True on success, False if no image in response
    # 9:16 aspect ratio
    # Validates: response has inline_data with image
```

This is now a **dumb pipe**. It takes a prompt string, calls Gemini, saves the image. No prompt templates, no scene type logic. That's all in `script.py` now.

---

### modules/audio.py

ElevenLabs TTS. Refactored from the per-scene audio logic in `step3_generate_voiceover.py`.

```python
def generate_audio(narration_text, output_path, voice_id=GAURAV_VOICE_ID) -> float
    # If scene should be silent (empty narration or quiz/leaderboard):
    #   Generate silence MP3 of appropriate duration
    #   Return the duration
    # Else:
    #   Call ElevenLabs API (eleven_multilingual_v2)
    #   Save MP3 to output_path
    #   Measure actual duration via ffprobe
    #   Return duration in seconds

def generate_silence(duration_seconds, output_path) -> float
    # FFmpeg: generate silent MP3 of given duration
    # Used for quiz, quiz_answer, leaderboard scenes
    # Return duration
```

Voice: Gaurav (`SXuKWBhKoIoAHKlf6Gt3`), Indian English.
Silence padding per scene type (from memory file):
- content: +1.0s padding
- quiz: +4.0s (thinking time)
- quiz_answer: +1.5s
- leaderboard: silence only

---

### modules/stitch.py

FFmpeg stitcher. Refactored from `step4_stitch_video.py`.

```python
def stitch(output_dir, logo_path=None, bg_music_path=None) -> str
    # Reads manifest.json for scene order and audio durations
    # For each scene:
    #   image = scenes/scene_XX/image.png
    #   audio = scenes/scene_XX/audio.mp3
    #   duration = audio_duration from manifest
    # FFmpeg filter chain:
    #   1. Scale all images to 1080x1920
    #   2. Crossfade transitions (0.5s)
    #   3. Logo overlay (optional)
    #   4. Mix voiceover + background music (8% volume)
    # Output: output_dir/video.mp4
    # Returns path to video
```

Same FFmpeg logic as current `step4_stitch_video.py`. Just reads from the new directory structure and manifest instead of the old frames manifest.

---

### modules/styles.py

Role-based configuration. No logic — just data.

```python
STYLES = {
    "doctor": {
        "narration_tone": (
            "Clinical, peer-to-peer, evidence-based. Use medical terminology. "
            "Speak to a physician who prescribes medications."
        ),
        "visual_style": (
            "Background: vivid blue gradient from royal blue at top to sky blue at bottom. "
            "Typography: white sans-serif, clean and modern. Maximum 2-3 lines of text visible. "
            "No clutter. Do NOT render instructions as text in the image. "
            "Do NOT include phones, smartphones, hands, devices, cameras, or watermarks. "
            "9:16 portrait format."
        ),
        "content_depth": "Deep — MOA, pharmacokinetics, drug interactions, receptor-level detail.",
        "voice_id": "SXuKWBhKoIoAHKlf6Gt3",  # Gaurav
        "scene_padding": {
            "content": 1.0,
            "quiz_intro": 1.0,
            "quiz": 4.0,
            "quiz_answer": 1.5,
            "score": 1.5,
            "cta": 1.5,
            "leaderboard": 0.0,
        },
        "silent_scene_types": ["quiz", "quiz_answer", "leaderboard"],
    },
    "field": {
        "narration_tone": (
            "Simple, conversational, like a company rep explaining the product. "
            "Avoid medical jargon. Speak to a pharmacy retailer or stockist."
        ),
        "visual_style": (
            "Background: warm dark charcoal with soft tones. "
            "Rounded sans-serif text, larger sizes. Colorful badge-style icons (orange, teal). "
            "NO tables or clinical diagrams. 1-2 text points per frame max. "
            "Friendly, product-training feel. 9:16 portrait format. "
            "Do NOT include phones, smartphones, hands, devices, cameras, or watermarks."
        ),
        "content_depth": "Practical — what it treats, customer questions, storage, when to recommend.",
        "voice_id": "SXuKWBhKoIoAHKlf6Gt3",  # Gaurav (same for now)
        "scene_padding": {
            "content": 1.0,
            "quiz_intro": 1.0,
            "quiz": 4.0,
            "quiz_answer": 1.5,
            "score": 1.5,
            "cta": 1.5,
            "leaderboard": 0.0,
        },
        "silent_scene_types": ["quiz", "quiz_answer", "leaderboard"],
    },
}
```

---

## generate.py — the entry point

```
Usage:
  python generate.py <pdf_path> <role>                   # full run
  python generate.py --retry <output_dir>                # retry all failed
  python generate.py --retry <output_dir> --scene 3      # retry scene 3 (both image + audio)
  python generate.py --retry <output_dir> --scene 3 --step image   # retry scene 3 image only
  python generate.py --stitch <output_dir>               # just re-run stitch (after manual edits)
```

### Full run flow:

```python
def run(pdf_path, role):
    product = detect_product_name(pdf_path)  # from filename
    output_dir = f"output/{product.lower()}_{role}"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(f"{output_dir}/scenes", exist_ok=True)

    # --- PHASE 1: PLAN ---
    print("Phase 1: Plan")

    text_path = extract.extract(pdf_path, output_dir)
    script = script.generate_script(text_path, role, output_dir)

    # Create manifest with all scenes pending
    manifest.create(output_dir, pdf_path, role, product, script["scenes"])

    # --- PHASE 2: GENERATE (parallel) ---
    print(f"Phase 2: Generate ({len(script['scenes'])} scenes)")

    style = styles.STYLES[role]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []

        for scene in script["scenes"]:
            num = scene["scene_number"]
            scene_dir = f"{output_dir}/scenes/scene_{num:02d}"
            os.makedirs(scene_dir, exist_ok=True)

            # Submit image generation
            futures.append(pool.submit(
                generate_scene_image,
                output_dir, scene, scene_dir
            ))

            # Submit audio generation
            futures.append(pool.submit(
                generate_scene_audio,
                output_dir, scene, scene_dir, style
            ))

        # Wait for all, collect results
        for future in as_completed(futures):
            future.result()  # exceptions logged in the task functions

    # --- PHASE 3: ASSEMBLE ---
    if manifest.all_scenes_ready(output_dir):
        print("Phase 3: Assemble")
        video_path = stitch.stitch(output_dir)
        manifest.set_video_status(output_dir, "done")
        print(f"Done: {video_path}")
    else:
        failed = manifest.get_failed(output_dir)
        print(f"Phase 3: Skipped — {len(failed)} tasks failed:")
        for f in failed:
            print(f"  scene {f['scene']} {f['step']}: {f.get('error', 'unknown')}")
        print(f"\nRetry: python generate.py --retry {output_dir}")


def generate_scene_image(output_dir, scene, scene_dir):
    """Generate image for one scene. Updates manifest."""
    num = scene["scene_number"]
    out_path = f"{scene_dir}/image.png"
    try:
        success = image.generate_image(scene["visual_prompt"], out_path)
        if success:
            manifest.update_scene(output_dir, num, "image", "done")
        else:
            manifest.update_scene(output_dir, num, "image", "failed",
                                  error="No image in Gemini response")
    except Exception as e:
        manifest.update_scene(output_dir, num, "image", "failed", error=str(e))


def generate_scene_audio(output_dir, scene, scene_dir, style):
    """Generate audio for one scene. Updates manifest."""
    num = scene["scene_number"]
    scene_type = scene.get("scene_type", "content")
    out_path = f"{scene_dir}/audio.mp3"

    try:
        if scene_type in style["silent_scene_types"]:
            # Silent scene — generate silence with appropriate padding
            padding = style["scene_padding"].get(scene_type, 2.0)
            duration = audio.generate_silence(padding, out_path)
        else:
            duration = audio.generate_audio(
                scene["narration"], out_path,
                voice_id=style["voice_id"]
            )
            # Add padding
            padding = style["scene_padding"].get(scene_type, 1.0)
            duration += padding

        manifest.update_scene(output_dir, num, "audio", "done",
                              audio_duration=duration)
    except Exception as e:
        manifest.update_scene(output_dir, num, "audio", "failed", error=str(e))
```

### Retry flow:

```python
def retry(output_dir, scene_filter=None, step_filter=None):
    failed = manifest.get_failed(output_dir, step=step_filter, scene=scene_filter)

    if not failed:
        print("Nothing to retry — all done!")
        return

    print(f"Retrying {len(failed)} failed tasks...")
    script = load_script(output_dir)
    style = styles.STYLES[manifest.load(output_dir)["role"]]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for item in failed:
            scene = get_scene(script, item["scene"])
            scene_dir = f"{output_dir}/scenes/scene_{item['scene']:02d}"

            if item["step"] == "image":
                futures.append(pool.submit(
                    generate_scene_image, output_dir, scene, scene_dir
                ))
            elif item["step"] == "audio":
                futures.append(pool.submit(
                    generate_scene_audio, output_dir, scene, scene_dir, style
                ))

        for future in as_completed(futures):
            future.result()

    # Check if we can stitch now
    if manifest.all_scenes_ready(output_dir):
        print("All scenes ready — stitching...")
        stitch.stitch(output_dir)
```

---

## How it handles the problems we identified

| Problem | How it's solved |
|---------|----------------|
| Scene 5 image fails → had to re-run everything | Manifest tracks per-scene status. Retry only scene 5 image. |
| Can't tell what succeeded/failed | `manifest.json` — one look tells you everything |
| Prompt templates hardcoded for AllerDuo | Claude generates `visual_prompt` per scene. `image.py` is a dumb pipe. Works for any product. |
| Content scenes mapped by scene number (1→intro, 2→composition) | Claude decides scene structure. No hardcoded mapping. |
| Audio-video sync drift | Per-scene audio with measured duration. Same approach as current v4 (which works). |
| Gemini returns text instead of image | `image.py` validates response, marks as `failed` if no image. Retry later. |
| Want to manually fix an image | Replace `scene_03/image.png` with your own file. Run `--stitch` to rebuild video. |

---

## Build order

| # | File | What to do | Based on |
|---|------|-----------|----------|
| 1 | `modules/manifest.py` | Write from scratch | New |
| 2 | `modules/styles.py` | Write from scratch | Config extracted from current code + memory file |
| 3 | `modules/extract.py` | Copy + simplify from `step1_extract.py` | Existing |
| 4 | `modules/image.py` | Extract `generate_frame()` from `step3_generate_frames.py`, remove prompt logic | Existing |
| 5 | `modules/audio.py` | Extract per-scene audio logic from `step3_generate_voiceover.py` | Existing |
| 6 | `modules/script.py` | Refactor `step2_generate_script.py` — add `visual_prompt` generation | Existing (biggest change) |
| 7 | `modules/stitch.py` | Refactor `step4_stitch_video.py` — read from manifest + new dir structure | Existing |
| 8 | `generate.py` | Write orchestrator — phases, parallel, retry, stitch-only | New |

**Suggested order**: 1 → 2 → 3 → 4 → 5 → 6 → test script+image end-to-end → 7 → 8 → full test

---

## Testing plan

### Test 1: Script + Image (after steps 1-6)
```bash
# Manually:
python -c "
from modules import extract, script, image
text = extract.extract('path/to/AllerDuo.pdf', '/tmp/test')
s = script.generate_script(text, 'doctor', '/tmp/test')
image.generate_image(s['scenes'][0]['visual_prompt'], '/tmp/test_scene1.png')
"
# Check: does /tmp/test_scene1.png look right?
```

### Test 2: Audio (after step 5)
```bash
python -c "
from modules import audio
dur = audio.generate_audio('Meet AllerDuo, a dual-action tablet.', '/tmp/test_audio.mp3')
print(f'Duration: {dur}s')
"
```

### Test 3: Full pipeline (after step 8)
```bash
python generate.py "../JagsonPal Pharma - L&D Content/AllerDuo.pdf" doctor
# Check output/allerduo_doctor/manifest.json
# Check output/allerduo_doctor/scenes/scene_01/image.png
# Check output/allerduo_doctor/video.mp4
```

### Test 4: Retry
```bash
# Manually delete scene 3 image to simulate failure
rm output/allerduo_doctor/scenes/scene_03/image.png
# Edit manifest: set scene 3 image to "failed"
python generate.py --retry output/allerduo_doctor/ --scene 3 --step image
```

### Test 5: Different product
```bash
python generate.py "../JagsonPal Pharma - L&D Content/Tibrolin_Trypsin + Bromelain + Rutoxide.pdf" doctor
# This is the real generalization test — no AllerDuo-specific code should exist
```
