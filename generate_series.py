"""
Generate a full video series from a single PDF.

Runs the complete pipeline for every topic the content analysis says is possible:
  PDF -> Extract -> Analyze -> (Script + Frames + Voiceover + Stitch) x N topics

Usage:
  python generate_series.py <pdf_path> [profile] [--tts elevenlabs|gemini] [--voice name] [--mode demo|production]

Examples:
  python generate_series.py "pdfs/AllerDuo.pdf"
  python generate_series.py "pdfs/Tibrolin_Trypsin + Bromelain + Rutoxide.pdf" retailer
  python generate_series.py "pdfs/AllerDuo.pdf" doctor --tts gemini --voice kore

Required env vars:
  ANTHROPIC_API_KEY   - Claude API for script gen + analysis
  GOOGLE_API_KEY      - Gemini for frames (+ TTS if --tts gemini)
  ELEVENLABS_API_KEY  - ElevenLabs TTS (if --tts elevenlabs, the default)
"""

from __future__ import annotations

import sys
import os
import json
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def output_path(relative: str) -> str:
    return os.path.join(BASE_DIR, relative)


def output_exists(relative: str) -> bool:
    return os.path.exists(output_path(relative))


def run(cmd: list[str], label: str) -> int:
    print(f"\n{'─'*50}")
    print(f"  {label}")
    print(f"{'─'*50}\n")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    pdf_path = os.path.abspath(sys.argv[1])
    profile = "doctor"
    voice = "gaurav"
    tts = "elevenlabs"
    mode = "demo"

    i = 2
    positional = 0
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--tts":
            tts = sys.argv[i + 1]
            i += 2
        elif arg == "--voice":
            voice = sys.argv[i + 1]
            i += 2
        elif arg == "--mode":
            mode = sys.argv[i + 1]
            i += 2
        else:
            if positional == 0:
                profile = arg
            positional += 1
            i += 1

    python = sys.executable
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]

    # Check env vars
    required = ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]
    if tts == "elevenlabs":
        required.append("ELEVENLABS_API_KEY")
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"  SERIES GENERATION")
    print(f"  PDF: {os.path.basename(pdf_path)}")
    print(f"  Profile: {profile}")
    print(f"  TTS: {tts} / {voice}")
    print(f"{'='*60}")

    start_time = time.time()

    # ── Step 1: Extract ──
    text_file = f"output/{base_name}.md"
    txt_file = f"output/{base_name}.txt"
    if not output_exists(text_file):
        rc = run([python, "step1_extract.py", pdf_path], "Step 1: Extract PDF")
        if rc != 0:
            print("Extraction failed")
            sys.exit(1)
    else:
        print(f"\n  [skip] {text_file} exists")

    # ── Step 1b: Analyze ──
    analysis_file = f"output/{base_name}_analysis.json"
    if not output_exists(analysis_file):
        input_file = text_file if output_exists(text_file) else txt_file
        rc = run([python, "step1b_analyze_content.py", input_file], "Step 1b: Analyze Content")
        if rc != 0:
            print("Analysis failed")
            sys.exit(1)
    else:
        print(f"  [skip] {analysis_file} exists")

    # Load analysis
    with open(output_path(analysis_file)) as f:
        analysis = json.load(f)

    product = analysis.get("product_name", base_name)
    topics = analysis.get("recommended_reel_order", [])

    if not topics:
        print("No topics found in analysis. Nothing to generate.")
        sys.exit(0)

    print(f"\n  Product: {product}")
    print(f"  Topics to generate: {', '.join(topics)} ({len(topics)} reels)")

    # ── Generate each reel ──
    results = []

    for reel_num, topic in enumerate(topics, 1):
        print(f"\n{'='*60}")
        print(f"  REEL {reel_num}/{len(topics)}: {topic}")
        print(f"{'='*60}")

        script_file = f"output/{base_name}_{profile}_{topic}_script.json"
        frames_manifest = f"output/{base_name}_{profile}_{topic}_script_frames.json"
        audio_file = f"output/{base_name}_{profile}_{topic}_script_{voice}.mp3"
        durations_file = f"output/{base_name}_{profile}_{topic}_script_durations.json"
        video_file = f"output/{base_name}_{profile}_{topic}_script_v1_video.mp4"
        validation_file = f"output/{base_name}_{profile}_{topic}_script_validation.json"

        reel_ok = True

        # Step 2: Script
        if output_exists(script_file):
            print(f"  [skip] script exists")
        else:
            cmd = [python, "step2_generate_script.py", txt_file, profile, topic, analysis_file, "--mode", mode]
            rc = run(cmd, f"Script ({topic})")
            if rc != 0:
                print(f"  [FAIL] script generation")
                results.append({"topic": topic, "status": "failed", "step": "script"})
                continue

        # Step 2b: Validate script
        if output_exists(validation_file):
            print(f"  [skip] validation exists")
        else:
            rc = run(
                [python, "validate_script.py", script_file, txt_file],
                f"Validate ({topic})",
            )
            if rc != 0:
                print(f"  [WARN] validation failed (continuing anyway)")

        # Step 3a+3b: Frames + Voiceover in parallel
        need_frames = not output_exists(frames_manifest)
        need_voice = not output_exists(audio_file)

        if not need_frames:
            print(f"  [skip] frames exist")
        if not need_voice:
            print(f"  [skip] voiceover exists")

        if need_frames or need_voice:
            frame_cmd = [python, "step3_generate_frames.py", script_file]
            if tts == "elevenlabs":
                vo_cmd = [python, "step3_generate_voiceover.py", script_file, voice]
            else:
                vo_cmd = [python, "step3b_generate_voiceover.py", script_file, voice]

            if need_frames and need_voice:
                print(f"\n  Running Frames + Voiceover in parallel...")
                with ThreadPoolExecutor(max_workers=2) as pool:
                    f_future = pool.submit(run, frame_cmd, f"Frames ({topic})")
                    v_future = pool.submit(run, vo_cmd, f"Voiceover ({topic})")
                    f_rc = f_future.result()
                    v_rc = v_future.result()
                if f_rc != 0:
                    print(f"  [FAIL] frame generation")
                    results.append({"topic": topic, "status": "failed", "step": "frames"})
                    continue
                if v_rc != 0:
                    print(f"  [FAIL] voiceover generation")
                    results.append({"topic": topic, "status": "failed", "step": "voiceover"})
                    continue
            elif need_frames:
                rc = run(frame_cmd, f"Frames ({topic})")
                if rc != 0:
                    print(f"  [FAIL] frame generation")
                    results.append({"topic": topic, "status": "failed", "step": "frames"})
                    continue
            elif need_voice:
                rc = run(vo_cmd, f"Voiceover ({topic})")
                if rc != 0:
                    print(f"  [FAIL] voiceover generation")
                    results.append({"topic": topic, "status": "failed", "step": "voiceover"})
                    continue

        # Step 4: Stitch
        if output_exists(video_file):
            print(f"  [skip] video exists")
        else:
            stitch_cmd = [
                python, "step4_stitch_video.py",
                frames_manifest, audio_file, script_file,
                "--durations", durations_file,
                "--suffix", "_v1",
            ]
            rc = run(stitch_cmd, f"Stitch ({topic})")
            if rc != 0:
                print(f"  [FAIL] video stitching")
                results.append({"topic": topic, "status": "failed", "step": "stitch"})
                continue

        results.append({"topic": topic, "status": "ok", "video": video_file})

    # ── Summary ──
    elapsed = time.time() - start_time
    ok_count = sum(1 for r in results if r["status"] == "ok")
    fail_count = sum(1 for r in results if r["status"] == "failed")

    print(f"\n{'='*60}")
    print(f"  SERIES COMPLETE")
    print(f"{'='*60}")
    print(f"\n  Product: {product}")
    print(f"  Profile: {profile}")
    print(f"  Reels generated: {ok_count}/{len(topics)}")
    if fail_count:
        print(f"  Failed: {fail_count}")
    print(f"  Time: {elapsed/60:.1f} minutes\n")

    for r in results:
        if r["status"] == "ok":
            print(f"  [OK]   {r['topic']:<16} -> {r['video']}")
        else:
            print(f"  [FAIL] {r['topic']:<16} (step: {r['step']})")

    # Save series manifest
    series_manifest = f"output/{base_name}_{profile}_series.json"
    with open(output_path(series_manifest), "w") as f:
        json.dump({
            "product_name": product,
            "profile": profile,
            "tts": tts,
            "voice": voice,
            "total_reels": len(topics),
            "completed": ok_count,
            "failed": fail_count,
            "elapsed_seconds": round(elapsed, 1),
            "reels": results,
        }, f, indent=2)

    print(f"\n  Series manifest: {series_manifest}")


if __name__ == "__main__":
    main()
