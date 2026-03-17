"""
Step 3b: Generate voiceover audio from script using Gemini TTS.

Generates audio PER SCENE for tight audio-visual sync (matching step 3 behavior).
Each scene gets its own audio clip with measured duration.
Outputs a durations manifest for the stitcher.

Prerequisites:
  - Set env var: GOOGLE_API_KEY
  - FFmpeg installed (for WAV to MP3 conversion and duration measurement)
"""

import json
import sys
import os
import wave
import subprocess
from google import genai
from google.genai import types

from config_loader import load_models, load_tts_gemini_template

_models = load_models()
_gemini_cfg = _models["voiceover_gemini"]
_timing = _models["scene_timing"]

MODEL = _gemini_cfg["model"]
VOICES = {v.lower(): v for v in _gemini_cfg["voices"]}
MIN_DURATIONS = _timing["min_durations"]
PADDING = _timing["padding"]
TTS_TEMPLATE = load_tts_gemini_template()


def save_wav(filename: str, pcm_data: bytes):
    """Save raw PCM data as WAV file."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(24000)
        wf.writeframes(pcm_data)


def wav_to_mp3(wav_path: str, mp3_path: str):
    """Convert WAV to MP3 using FFmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-b:a", "128k", mp3_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg WAV->MP3 conversion failed: {result.stderr[-300:]}")
    if os.path.exists(wav_path):
        os.remove(wav_path)


def get_audio_duration(path: str) -> float:
    """Get duration of an audio file using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def generate_silence(duration: float, out_path: str):
    """Generate a silent MP3 of given duration using FFmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anullsrc=r=24000:cl=mono", "-t", str(duration),
         "-b:a", "128k", out_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg silence generation failed: {result.stderr[-300:]}")


def concat_audio_files(file_list: list, out_path: str):
    """Concatenate MP3 files using FFmpeg concat demuxer."""
    import tempfile
    fd, list_path = tempfile.mkstemp(prefix="gemini_audio_concat_", suffix=".txt")
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


def generate_scene_audio(client, text: str, voice_name: str, out_path: str) -> float:
    """Generate audio for a single scene using Gemini TTS. Returns duration in seconds."""
    tts_prompt = TTS_TEMPLATE.format(text=text)

    response = client.models.generate_content(
        model=MODEL,
        contents=tts_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
        ),
    )

    pcm_data = response.candidates[0].content.parts[0].inline_data.data

    wav_path = out_path.replace(".mp3", ".wav")
    save_wav(wav_path, pcm_data)
    wav_to_mp3(wav_path, out_path)

    return get_audio_duration(out_path)


def generate_voiceover(script_path: str, voice_key: str = "kore"):
    import shutil
    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg not found. Install with: brew install ffmpeg")
        sys.exit(1)

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: Set GOOGLE_API_KEY env var")
        sys.exit(1)

    voice_name = VOICES.get(voice_key)
    if not voice_name:
        print(f"Unknown voice: {voice_key}")
        print(f"Options: {', '.join(VOICES.keys())}")
        sys.exit(1)

    with open(script_path) as f:
        script = json.load(f)

    client = genai.Client(api_key=api_key)

    os.makedirs("output", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(script_path))[0]
    audio_dir = f"output/{base_name}_audio_gemini"
    os.makedirs(audio_dir, exist_ok=True)

    print(f"Generating per-scene voiceover: voice={voice_name}")
    print(f"Model: {MODEL}\n")

    scene_audio_files = []
    scene_durations = []

    # Phase 1: Generate all TTS audio in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed

    narrated_scenes = [s for s in script["scenes"] if s.get("narration", "").strip()]

    tts_results = {}  # scene_num -> (mp3_path, audio_dur)
    if narrated_scenes:
        max_workers = min(len(narrated_scenes), 5)
        print(f"  Generating {len(narrated_scenes)} TTS clips in parallel ({max_workers} workers)...")

        def _tts_one(scene):
            sn = scene["scene_number"]
            mp3 = f"{audio_dir}/scene_{sn:02d}.mp3"
            dur = generate_scene_audio(client, scene["narration"].strip(), voice_name, mp3)
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
        print("Usage: python step3b_generate_voiceover.py <script.json> [voice]")
        print(f"  voice options: {', '.join(VOICES.keys())}")
        sys.exit(1)

    script_path = sys.argv[1]
    voice_key = sys.argv[2] if len(sys.argv) > 2 else "kore"

    generate_voiceover(script_path, voice_key)


if __name__ == "__main__":
    main()
