"""
Step 3: Generate voiceover audio from script using ElevenLabs TTS.

Generates audio PER SCENE for tight audio-visual sync.
Each scene gets its own audio clip, with measured duration.
The frame manifest is updated with actual audio durations.

For quiz scenes, SSML <break> tags add pauses so the viewer has time to read.

Prerequisites:
  - pip install elevenlabs
  - Set env var: ELEVENLABS_API_KEY
"""

from __future__ import annotations
import json
import sys
import os
import base64
import struct
import subprocess

from config_loader import load_models

_models = load_models()
_el_cfg = _models["voiceover_elevenlabs"]
_timing = _models["scene_timing"]

VOICES = {k: {"id": v["id"], "name": k.title(), "desc": v["desc"]} for k, v in _el_cfg["voices"].items()}
MIN_DURATIONS = _timing["min_durations"]
PADDING = _timing["padding"]


def get_audio_duration(mp3_path: str) -> float:
    """Get duration of an MP3 file using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", mp3_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def generate_scene_audio(client, text: str, voice_id: str, out_path: str) -> float:
    """Generate audio for a single scene, return duration in seconds."""
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=_el_cfg["model"],
        output_format="mp3_44100_128",
    )
    data = b"".join(audio)
    with open(out_path, "wb") as f:
        f.write(data)
    return get_audio_duration(out_path)


def generate_silence(duration: float, out_path: str):
    """Generate a silent MP3 of given duration using FFmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anullsrc=r=44100:cl=mono", "-t", str(duration),
         "-b:a", "128k", out_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg silence generation failed: {result.stderr[-300:]}")


def concat_audio_files(file_list: list, out_path: str):
    """Concatenate MP3 files using FFmpeg concat demuxer."""
    import tempfile
    fd, list_path = tempfile.mkstemp(prefix="audio_concat_", suffix=".txt")
    os.close(fd)
    try:
        with open(list_path, "w") as f:
            for path in file_list:
                f.write(f"file '{os.path.abspath(path)}'\n")

        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", list_path, "-c", "copy", out_path],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-300:]}")
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)


def generate_voiceover(script_path: str, voice_key: str = "gaurav") -> str:
    import shutil
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found. Install with: brew install ffmpeg (or add to packages.txt for Streamlit Cloud)")

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY env var not set")

    voice = VOICES.get(voice_key)
    if not voice:
        raise RuntimeError(f"Unknown voice: {voice_key}. Options: {', '.join(VOICES.keys())}")

    with open(script_path) as f:
        script = json.load(f)

    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=api_key)

    os.makedirs("output", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(script_path))[0]
    audio_dir = f"output/{base_name}_audio"
    os.makedirs(audio_dir, exist_ok=True)

    print(f"Generating per-scene voiceover: voice={voice['name']}")
    print(f"  {voice['desc']}\n")

    scene_audio_files = []
    scene_durations = []

    # Phase 1: Generate all TTS audio in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed

    narrated_scenes = []
    silent_scenes = []
    for scene in script["scenes"]:
        narration = scene.get("narration", "").strip()
        if narration:
            narrated_scenes.append(scene)
        else:
            silent_scenes.append(scene)

    # Parallel TTS calls
    tts_results = {}  # scene_num -> (mp3_path, audio_dur)
    if narrated_scenes:
        max_workers = min(len(narrated_scenes), 5)
        print(f"  Generating {len(narrated_scenes)} TTS clips in parallel ({max_workers} workers)...")

        def _tts_one(scene):
            sn = scene["scene_number"]
            mp3 = f"{audio_dir}/scene_{sn:02d}.mp3"
            for attempt in range(3):
                try:
                    dur = generate_scene_audio(client, scene["narration"].strip(), voice["id"], mp3)
                    return sn, mp3, dur
                except Exception as e:
                    if "409" in str(e) or "already_running" in str(e):
                        import time as _time
                        _time.sleep(2 * (attempt + 1))
                        continue
                    raise
            # Final attempt without catch
            dur = generate_scene_audio(client, scene["narration"].strip(), voice["id"], mp3)
            return sn, mp3, dur

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_tts_one, s): s for s in narrated_scenes}
            for future in as_completed(futures):
                sn, mp3, dur = future.result()
                tts_results[sn] = (mp3, dur)

    # Phase 2: Sequential ordering, padding, and silence generation
    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        scene_type = scene.get("scene_type", "content")
        narration = scene.get("narration", "").strip()
        min_dur = MIN_DURATIONS.get(scene_type, 5.0)
        padding = PADDING.get(scene_type, 1.0)

        scene_mp3 = f"{audio_dir}/scene_{scene_num:02d}.mp3"

        if narration and scene_num in tts_results:
            _, audio_dur = tts_results[scene_num]
            scene_dur = max(audio_dur + padding, min_dur)

            if scene_dur > audio_dur:
                silence_path = f"{audio_dir}/silence_{scene_num:02d}.mp3"
                generate_silence(scene_dur - audio_dur, silence_path)
                padded_path = f"{audio_dir}/scene_{scene_num:02d}_padded.mp3"
                concat_audio_files([scene_mp3, silence_path], padded_path)
                os.rename(padded_path, scene_mp3)
                os.remove(silence_path)

            print(f"  Scene {scene_num:2d} [{scene_type:<12}] {audio_dur:.1f}s audio -> {scene_dur:.1f}s total")
        else:
            scene_dur = min_dur
            generate_silence(scene_dur, scene_mp3)
            print(f"  Scene {scene_num:2d} [{scene_type:<12}] silence -> {scene_dur:.1f}s")

        scene_audio_files.append(scene_mp3)
        scene_durations.append(scene_dur)

    # Concatenate all scene audio into one file
    out_path = f"output/{base_name}_{voice_key}.mp3"
    concat_audio_files(scene_audio_files, out_path)

    total_dur = sum(scene_durations)
    print(f"\nTotal: {total_dur:.1f}s -> {out_path}")

    # Save scene durations manifest for the stitcher
    durations_path = f"output/{base_name}_durations.json"
    dur_data = []
    for scene, dur in zip(script["scenes"], scene_durations):
        dur_data.append({
            "scene_number": scene["scene_number"],
            "scene_type": scene.get("scene_type", "content"),
            "duration": round(dur, 2),
        })
    with open(durations_path, "w") as f:
        json.dump(dur_data, f, indent=2)
    print(f"Scene durations -> {durations_path}")

    return out_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python step3_generate_voiceover.py <script.json> [voice]")
        print(f"  voice options: {', '.join(VOICES.keys())}")
        sys.exit(1)

    script_path = sys.argv[1]
    voice_key = sys.argv[2] if len(sys.argv) > 2 else "gaurav"

    generate_voiceover(script_path, voice_key)


if __name__ == "__main__":
    main()
