"""
Unified pipeline orchestrator with progress callbacks.

Used by app.py (Streamlit) and can also be called programmatically.
Imports step functions directly — no subprocess overhead.
"""

from __future__ import annotations
import gc
import json
import os
import time
import tempfile
import subprocess
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
load_dotenv()

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"

# Pipeline step imports (deferred to avoid slow import at module level)
_imports_loaded = False


def _ensure_imports():
    global _imports_loaded
    if _imports_loaded:
        return
    _imports_loaded = True
    # Just verify env is loaded — actual imports happen in run_pipeline


@dataclass
class PipelineConfig:
    pdf_path: str
    profile: str = "sales_executive"
    topic: str = "intro"
    voice: str = "gaurav"
    tts: str = "elevenlabs"
    mode: str = "demo"
    guidance: str = ""
    language: str = "en"


ProgressCallback = Callable[[str, str, float], None]


def _noop_progress(step: str, message: str, pct: float):
    pass


def run_pipeline(config: PipelineConfig, on_progress: ProgressCallback | None = None) -> dict:
    """Run the full pipeline end-to-end. Returns dict with video_path, duration, error."""
    if on_progress is None:
        on_progress = _noop_progress

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    base_name = Path(config.pdf_path).stem

    # Check env vars
    required = ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]
    if config.tts == "elevenlabs":
        required.append("ELEVENLABS_API_KEY")
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        return {"video_path": None, "duration": 0, "error": f"Missing env vars: {', '.join(missing)}"}

    try:
        # --- Step 1: Extract ---
        on_progress("extract", "Extracting text from PDF...", 0.05)
        text_path = OUTPUT_DIR / f"{base_name}.md"
        txt_path = OUTPUT_DIR / f"{base_name}.txt"

        if not text_path.exists():
            from step1_extract import extract_pdf
            text, method = extract_pdf(config.pdf_path)
            text_path.write_text(text)
            txt_path.write_text(text)

        # --- Step 1b: Analyze ---
        on_progress("analyze", "Analyzing content structure...", 0.12)
        analysis_path = OUTPUT_DIR / f"{base_name}_analysis.json"
        analysis = None

        if not analysis_path.exists():
            from step1b_analyze_content import analyze_content
            content = text_path.read_text()
            analysis = analyze_content(content)
            analysis_path.write_text(json.dumps(analysis, indent=2))
        else:
            analysis = json.loads(analysis_path.read_text())

        gc.collect()

        # --- Step 2: Script outline (no image_prompt) ---
        on_progress("script", "Generating script outline...", 0.22)
        script_path = OUTPUT_DIR / f"{base_name}_{config.profile}_{config.topic}_script.json"

        if not script_path.exists():
            from step2_generate_script import (
                generate_script_outline, generate_script,
                generate_image_prompts, merge_image_prompts, filter_quiz_scenes,
            )
            pdf_text = txt_path.read_text()
            script = generate_script_outline(pdf_text, config.profile, config.topic, analysis, guidance=config.guidance, language=config.language)

            if config.mode == "production":
                full_path = script_path.with_name(script_path.stem + "_full.json")
                full_path.write_text(json.dumps(script, indent=2))
                script = filter_quiz_scenes(script)

            script_path.write_text(json.dumps(script, indent=2))
        else:
            from step2_generate_script import (
                generate_script, generate_image_prompts,
                merge_image_prompts, filter_quiz_scenes,
            )
            pdf_text = txt_path.read_text()

        # --- Step 3: Voice + Pillow templates + (image prompts → AI frames) in parallel ---
        on_progress("media", "Starting visual and audio generation...", 0.40)
        frames_manifest = OUTPUT_DIR / f"{base_name}_{config.profile}_{config.topic}_script_frames.json"
        audio_path = OUTPUT_DIR / f"{base_name}_{config.profile}_{config.topic}_script_{config.voice}.mp3"
        durations_path = OUTPUT_DIR / f"{base_name}_{config.profile}_{config.topic}_script_durations.json"

        need_frames = not frames_manifest.exists()
        need_voice = not audio_path.exists()

        def _gen_voice():
            if not need_voice:
                return
            if config.tts == "gemini":
                from step3b_generate_voiceover import generate_voiceover
            else:
                from step3_generate_voiceover import generate_voiceover
            generate_voiceover(str(script_path), config.voice)

        def _gen_frames_two_phase():
            """Generate frames: Pillow templates immediately, then image prompts → AI frames."""
            if not need_frames:
                return
            from step3_generate_frames import (
                generate_frame_ai, build_content_prompt, render_leaderboard,
                STYLE_BASE, MODEL,
            )
            from frame_templates import TEMPLATE_RENDERERS, render_content_fallback
            from config_loader import load_models
            from google import genai

            script_data = json.loads(script_path.read_text())
            scenes = script_data["scenes"]
            product_name = script_data["product_name"]
            lang = script_data.get("language", config.language)
            base = script_path.stem
            frames_dir = str(OUTPUT_DIR / f"{base}_frames")
            os.makedirs(frames_dir, exist_ok=True)

            results = {}  # scene_num -> (path, error_info)
            template_scenes = []
            ai_scenes = []

            for scene in scenes:
                scene["_language"] = lang
                scene_type = scene.get("scene_type", "content")
                scene_num = scene["scene_number"]
                filename = f"{frames_dir}/scene_{scene_num:02d}_{scene_type}.png"
                if scene_type == "content":
                    ai_scenes.append((scene, filename))
                else:
                    template_scenes.append((scene, filename))

            # Render Pillow template frames immediately (no API calls)
            for scene, filename in template_scenes:
                scene_type = scene.get("scene_type", "content")
                scene_num = scene["scene_number"]
                if scene_type == "leaderboard":
                    path = render_leaderboard(scene, filename)
                elif scene_type in TEMPLATE_RENDERERS:
                    path = TEMPLATE_RENDERERS[scene_type](scene, filename)
                else:
                    path = render_content_fallback(scene, filename)
                results[scene_num] = (path, None)

            on_progress("media", f"Rendered {len(template_scenes)} template frames — generating image descriptions...", 0.44)

            # Phase 2: Generate image prompts, then AI frames
            if ai_scenes:
                print("  Phase 2: Generating image prompts...")
                try:
                    img_prompts = generate_image_prompts(script_data, pdf_text)
                    merged = merge_image_prompts(script_data, img_prompts)
                    script_path.write_text(json.dumps(merged, indent=2))
                    # Update ai_scenes with merged image_prompts
                    merged_by_num = {s["scene_number"]: s for s in merged["scenes"]}
                    ai_scenes = [(merged_by_num[s["scene_number"]], fn) for s, fn in ai_scenes]
                except Exception as e:
                    print(f"  Image prompt generation failed: {e}")
                    print("  Retrying once...")
                    try:
                        img_prompts = generate_image_prompts(script_data, pdf_text)
                        merged = merge_image_prompts(script_data, img_prompts)
                        script_path.write_text(json.dumps(merged, indent=2))
                        merged_by_num = {s["scene_number"]: s for s in merged["scenes"]}
                        ai_scenes = [(merged_by_num[s["scene_number"]], fn) for s, fn in ai_scenes]
                    except Exception as e2:
                        print(f"  Retry failed: {e2}")
                        print("  Falling back to monolithic script generation...")
                        try:
                            full_script = generate_script(
                                pdf_text, config.profile, config.topic, analysis, guidance=config.guidance, language=config.language,
                            )
                            if config.mode == "production":
                                full_script = filter_quiz_scenes(full_script)
                            script_path.write_text(json.dumps(full_script, indent=2))
                            merged_by_num = {s["scene_number"]: s for s in full_script["scenes"]}
                            ai_scenes = [(merged_by_num[s["scene_number"]], fn) for s, fn in ai_scenes
                                         if s["scene_number"] in merged_by_num]
                        except Exception as e3:
                            print(f"  Monolithic fallback also failed: {e3}")
                            print("  Using Pillow fallback for all content scenes")
                            for scene, filename in ai_scenes:
                                path = render_content_fallback(scene, filename)
                                results[scene["scene_number"]] = (path, {"scene": scene["scene_number"], "error": "all generation failed"})
                            ai_scenes = []

                # Generate AI frames with Gemini
                if ai_scenes:
                    on_progress("media", f"Generating {len(ai_scenes)} AI frames with Gemini...", 0.50)
                    api_key = os.environ.get("GOOGLE_API_KEY")
                    client = genai.Client(api_key=api_key)
                    max_workers = min(len(ai_scenes), 3)
                    ai_done = [0]
                    ai_total = len(ai_scenes)

                    def _gen_one(scene_and_file):
                        scene, filename = scene_and_file
                        scene_num = scene["scene_number"]
                        prompt = build_content_prompt(scene)
                        path = generate_frame_ai(client, prompt, filename)
                        if path is None:
                            path = render_content_fallback(scene, filename)
                            return scene_num, path, {"scene": scene_num, "error": "AI failed, Pillow fallback"}
                        return scene_num, path, None

                    from concurrent.futures import as_completed
                    with ThreadPoolExecutor(max_workers=max_workers) as pool:
                        futures = {pool.submit(_gen_one, sf): sf for sf in ai_scenes}
                        for future in as_completed(futures):
                            sn, path, err = future.result()
                            results[sn] = (path, err)
                            ai_done[0] += 1
                            frame_pct = 0.50 + (ai_done[0] / ai_total) * 0.15
                            on_progress("media", f"Generated frame {ai_done[0]}/{ai_total}...", frame_pct)

            # Assemble manifest
            frame_paths = []
            errors = []
            for scene in scenes:
                sn = scene["scene_number"]
                path, err = results.get(sn, (None, None))
                if err:
                    errors.append(err)
                if path:
                    frame_paths.append({
                        "scene": sn,
                        "scene_type": scene.get("scene_type", "content"),
                        "path": path,
                        "duration": scene["duration_seconds"],
                    })

            manifest = {"product_name": product_name, "script_path": str(script_path), "frames": frame_paths}
            if errors:
                manifest["errors"] = errors
            frames_manifest.write_text(json.dumps(manifest, indent=2))

        # Run voice in background thread, frames on main thread
        # (frames uses its own ThreadPoolExecutor for Gemini — nesting that
        # inside another thread pool deadlocks Streamlit)
        voice_future = None
        if need_voice:
            voice_pool = ThreadPoolExecutor(max_workers=1)
            voice_future = voice_pool.submit(_gen_voice)

        if need_frames:
            _gen_frames_two_phase()

        if voice_future:
            on_progress("media", "Waiting for voiceover to finish...", 0.67)
            voice_future.result()
            voice_pool.shutdown(wait=False)

        # Free large text + collected API objects before FFmpeg steps
        del pdf_text
        gc.collect()

        # --- Step 4: Stitch ---
        on_progress("stitch", "Stitching video...", 0.70)
        video_path = OUTPUT_DIR / f"{base_name}_{config.profile}_{config.topic}_script_v1_video.mp4"

        if not video_path.exists():
            from step4_stitch_video import create_video
            logo = str(BASE_DIR / "assets" / "swishx_logo.png")
            result = create_video(
                str(frames_manifest),
                audio_path=str(audio_path),
                script_path=str(script_path),
                durations_path=str(durations_path),
                logo_path=logo if os.path.exists(logo) else None,
                bg_music_path=None,
                output_suffix="_v1",
            )
            if result is None:
                return {"video_path": None, "duration": 0, "error": "Video stitching failed"}

        gc.collect()

        # --- Step 5: Subtitles ---
        on_progress("subtitles", "Burning subtitles...", 0.85)
        subtitled_path = OUTPUT_DIR / f"{base_name}_{config.profile}_{config.topic}_script_v1_video_subtitled.mp4"

        if not subtitled_path.exists():
            from burn_subtitles import (
                enrich_drug_names, build_subtitle_events, build_box_ranges,
                generate_overlay_video, burn_onto_video,
            )

            script_data = json.loads(script_path.read_text())
            durations_data = json.loads(durations_path.read_text())
            sub_lang = script_data.get("language", config.language)
            enrich_drug_names(script_data)

            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True,
            )
            video_duration = float(probe.stdout.strip())

            events = build_subtitle_events(script_data, durations_data)
            box_ranges = build_box_ranges(script_data, durations_data)

            overlay_fd, overlay_path = tempfile.mkstemp(suffix=".mov", prefix="subtitle_overlay_")
            os.close(overlay_fd)

            try:
                overlay_result = generate_overlay_video(events, video_duration, overlay_path, box_ranges, language=sub_lang)
                if not overlay_result:
                    # Fall back to un-subtitled video
                    on_progress("done", "Done (subtitles skipped)", 1.0)
                    elapsed = time.time() - start_time
                    return {"video_path": str(video_path), "duration": elapsed, "error": None}

                burn_result = burn_onto_video(str(video_path), overlay_path, str(subtitled_path))
                if not burn_result:
                    on_progress("done", "Done (subtitles skipped)", 1.0)
                    elapsed = time.time() - start_time
                    return {"video_path": str(video_path), "duration": elapsed, "error": None}
            finally:
                if os.path.exists(overlay_path):
                    os.unlink(overlay_path)

        # --- Done ---
        elapsed = time.time() - start_time
        final_path = str(subtitled_path) if subtitled_path.exists() else str(video_path)
        on_progress("done", f"Complete! ({elapsed:.0f}s)", 1.0)

        return {"video_path": final_path, "duration": elapsed, "error": None}

    except Exception as e:
        elapsed = time.time() - start_time
        return {"video_path": None, "duration": elapsed, "error": str(e)}
