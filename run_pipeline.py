"""
Full Pipeline Runner: PDF -> Extract -> Analyze -> Script -> Voiceover + Frames -> Stitch

Run the entire pipeline end-to-end for one product + profile + topic.

Usage:
  python run_pipeline.py <pdf_path> [profile] [topic] [--voice gaurav] [--tts elevenlabs|gemini] [--all-topics] [--mode demo|production]

Examples:
  # Single reel
  python run_pipeline.py "pdfs/AllerDuo.pdf" doctor intro

  # All available reels for a product
  python run_pipeline.py "pdfs/AllerDuo.pdf" doctor --all-topics

  # Using Gemini TTS instead of ElevenLabs
  python run_pipeline.py "pdfs/AllerDuo.pdf" doctor intro --tts gemini --voice kore

Required env vars:
  ANTHROPIC_API_KEY   - Claude API key for script generation + content analysis
  GOOGLE_API_KEY      - Google API key for frame generation (+ Gemini TTS if using --tts gemini)
  ELEVENLABS_API_KEY  - ElevenLabs API key (if using --tts elevenlabs, the default)
"""

from __future__ import annotations

import sys
import os
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def output_exists(relative_path: str) -> bool:
    """Check if an output file already exists."""
    return os.path.exists(os.path.join(BASE_DIR, relative_path))


def run_step(step_name: str, cmd: list[str]) -> int:
    print(f"\n{'='*60}")
    print(f"  {step_name}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Parse arguments
    pdf_path = os.path.abspath(sys.argv[1])
    profile = "doctor"
    topic = None
    voice = "gaurav"
    tts = "elevenlabs"
    mode = "demo"
    guidance = ""
    all_topics = False

    i = 2
    positional = 0
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--voice":
            voice = sys.argv[i + 1]
            i += 2
        elif arg == "--tts":
            tts = sys.argv[i + 1]
            i += 2
        elif arg == "--mode":
            mode = sys.argv[i + 1]
            i += 2
        elif arg == "--guidance":
            guidance = sys.argv[i + 1]
            i += 2
        elif arg == "--all-topics":
            all_topics = True
            i += 1
        else:
            if positional == 0:
                profile = arg
            elif positional == 1:
                topic = arg
            positional += 1
            i += 1

    if not all_topics and topic is None:
        topic = "intro"

    python = sys.executable
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]

    # Check required env vars
    required = ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]
    if tts == "elevenlabs":
        required.append("ELEVENLABS_API_KEY")
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # --- Step 1: Extract text ---
    text_file = f"output/{base_name}.md"
    txt_file = f"output/{base_name}.txt"
    if not output_exists(text_file):
        rc = run_step("Step 1: Extract PDF Text", [python, "step1_extract.py", pdf_path])
        if rc != 0:
            print("Step 1 failed")
            sys.exit(1)
    else:
        print(f"\nSkipping Step 1: {text_file} already exists")

    # --- Step 1b: Analyze content ---
    analysis_file = f"output/{base_name}_analysis.json"
    if not output_exists(analysis_file):
        input_file = text_file if output_exists(text_file) else txt_file
        rc = run_step("Step 1b: Analyze Content Structure", [python, "step1b_analyze_content.py", input_file])
        if rc != 0:
            print("Step 1b failed (continuing without analysis)")
            analysis_file = None
    else:
        print(f"\nSkipping Step 1b: {analysis_file} already exists")

    # Determine which topics to generate
    if all_topics:
        if analysis_file and output_exists(analysis_file):
            with open(os.path.join(BASE_DIR, analysis_file)) as f:
                analysis = json.load(f)
            topics_to_run = analysis.get("recommended_reel_order", ["intro"])
            print(f"\nGenerating {len(topics_to_run)} reels: {', '.join(topics_to_run)}")
        else:
            topics_to_run = ["intro"]
            print("\nNo analysis available, defaulting to intro only")
    else:
        topics_to_run = [topic]

    # --- Generate each reel ---
    for reel_topic in topics_to_run:
        print(f"\n{'#'*60}")
        print(f"  REEL: {profile} / {reel_topic}")
        print(f"{'#'*60}")

        step2_input = txt_file
        script_file = f"output/{base_name}_{profile}_{reel_topic}_script.json"
        frames_manifest = f"output/{base_name}_{profile}_{reel_topic}_script_frames.json"
        audio_file = f"output/{base_name}_{profile}_{reel_topic}_script_{voice}.mp3"
        durations_file = f"output/{base_name}_{profile}_{reel_topic}_script_durations.json"
        video_file = f"output/{base_name}_{profile}_{reel_topic}_script_v1_video.mp4"

        # Step 2: Generate script
        if output_exists(script_file):
            print(f"\n  Skipping Step 2: {script_file} exists")
        else:
            cmd = [python, "step2_generate_script.py", step2_input, profile, reel_topic]
            if analysis_file:
                cmd.append(analysis_file)
            cmd.extend(["--mode", mode])
            if guidance:
                cmd.extend(["--guidance", guidance])
            rc = run_step(f"Step 2: Generate Script ({reel_topic})", cmd)
            if rc != 0:
                print(f"Step 2 failed for {reel_topic}, skipping reel")
                continue

        # Step 3a+3b: Generate frames + voiceover in parallel
        need_frames = not output_exists(frames_manifest)
        need_voice = not output_exists(audio_file)

        if not need_frames:
            print(f"  Skipping Step 3a: {frames_manifest} exists")
        if not need_voice:
            print(f"  Skipping Step 3b: {audio_file} exists")

        if need_frames or need_voice:
            frame_cmd = [python, "step3_generate_frames.py", script_file]
            if tts == "elevenlabs":
                voiceover_cmd = [python, "step3_generate_voiceover.py", script_file, voice]
            else:
                voiceover_cmd = [python, "step3b_generate_voiceover.py", script_file, voice]

            if need_frames and need_voice:
                print(f"\n{'='*60}")
                print(f"  Step 3a+3b: Frames + Voiceover in parallel ({reel_topic})")
                print(f"{'='*60}\n")
                with ThreadPoolExecutor(max_workers=2) as pool:
                    frame_future = pool.submit(run_step, "Frames", frame_cmd)
                    voice_future = pool.submit(run_step, "Voiceover", voiceover_cmd)
                    frame_rc = frame_future.result()
                    voice_rc = voice_future.result()
                if frame_rc != 0:
                    print(f"Step 3a failed for {reel_topic}, skipping reel")
                    continue
                if voice_rc != 0:
                    print(f"Step 3b failed for {reel_topic}, skipping reel")
                    continue
            elif need_frames:
                rc = run_step(f"Step 3a: Generate Frames ({reel_topic})", frame_cmd)
                if rc != 0:
                    print(f"Step 3a failed for {reel_topic}, skipping reel")
                    continue
            elif need_voice:
                rc = run_step(f"Step 3b: Generate Voiceover ({tts}, {voice})", voiceover_cmd)
                if rc != 0:
                    print(f"Step 3b failed for {reel_topic}, skipping reel")
                    continue

        # Step 4: Stitch video
        if output_exists(video_file):
            print(f"  Skipping Step 4: {video_file} exists")
        else:
            stitch_cmd = [
                python, "step4_stitch_video.py",
                frames_manifest, audio_file, script_file,
                "--durations", durations_file,
                "--suffix", "_v1",
            ]
            rc = run_step(f"Step 4: Stitch Video ({reel_topic})", stitch_cmd)
            if rc != 0:
                print(f"Step 4 failed for {reel_topic}")
                continue

        print(f"\n  Reel complete: {video_file}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"\nOutputs in ./output/")
    if all_topics:
        print(f"Generated reels for: {', '.join(topics_to_run)}")


if __name__ == "__main__":
    main()
