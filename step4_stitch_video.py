"""
Step 4: Stitch frames + voiceover + logo + subtitles + background music into video.

Takes:
  - Frames manifest (from step 3)
  - Voiceover MP3 (from step 3b)
  - Script JSON (for subtitle generation)
  - Logo PNG (optional)
  - Background music MP3 (optional)

Produces a final MP4 with:
  - Scene frames with crossfade transitions
  - Logo watermark (top-right corner)
  - Subtitles burned in (from narration text)
  - Voiceover + background music mixed

Prerequisites:
  - FFmpeg installed (brew install ffmpeg)
"""

from __future__ import annotations
import json
import sys
import os
import platform
import subprocess

from config_loader import load_models

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_stitch_cfg = load_models()["video_stitch"]


def _is_macos():
    return platform.system() == "Darwin"


def _get_encoder_args():
    """Return FFmpeg encoder args based on platform and config."""
    codec = _stitch_cfg.get("codec", "auto")
    preset = _stitch_cfg.get("preset", "fast")
    crf = _stitch_cfg.get("crf", 23)

    if codec == "auto" and _is_macos():
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=5,
            )
            if "h264_videotoolbox" in result.stdout:
                return ["-c:v", "h264_videotoolbox", "-q:v", "65"]
        except Exception:
            pass

    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
DEFAULT_LOGO = os.path.join(SCRIPT_DIR, "assets", "SwishX_White_logo.png")
BRANDING_LOGO = os.path.join(SCRIPT_DIR, "assets", "SwishX_White_logo.png")
DEFAULT_BG_MUSIC = os.path.join(SCRIPT_DIR, "assets", "bg_music_ambient.mp3")


def generate_srt(script_path: str, srt_path: str):
    """Generate SRT subtitle file from script narration."""
    with open(script_path) as f:
        script = json.load(f)

    srt_lines = []
    current_time = 0.0

    for i, scene in enumerate(script["scenes"]):
        narration = scene["narration"]
        duration = scene["duration_seconds"]

        # Split long narrations into 2 subtitle segments for readability
        words = narration.split()
        if len(words) > 20:
            mid = len(words) // 2
            # Find a good split point near the middle (at a comma or period)
            for j in range(mid - 3, mid + 3):
                if j < len(words) and words[j][-1] in ".,;:":
                    mid = j + 1
                    break
            segments = [" ".join(words[:mid]), " ".join(words[mid:])]
        else:
            segments = [narration]

        seg_duration = duration / len(segments)

        for seg_idx, segment in enumerate(segments):
            sub_num = len(srt_lines) + 1
            start = current_time + seg_idx * seg_duration
            end = start + seg_duration

            start_ts = format_timestamp(start)
            end_ts = format_timestamp(end)

            srt_lines.append(f"{sub_num}")
            srt_lines.append(f"{start_ts} --> {end_ts}")
            srt_lines.append(segment)
            srt_lines.append("")

        current_time += duration

    with open(srt_path, "w") as f:
        f.write("\n".join(srt_lines))

    return srt_path


def format_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(srt_path: str) -> list:
    """Parse SRT file into list of {start, end, text} dicts with times in seconds."""
    import re
    with open(srt_path) as f:
        content = f.read()

    blocks = re.split(r"\n\n+", content.strip())
    subs = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        # Parse timestamp line: 00:00:00,000 --> 00:00:05,000
        ts_match = re.match(r"(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)", lines[1])
        if not ts_match:
            continue
        start = srt_ts_to_seconds(ts_match.group(1))
        end = srt_ts_to_seconds(ts_match.group(2))
        text = " ".join(lines[2:])
        subs.append({"start": start, "end": end, "text": text})
    return subs


def srt_ts_to_seconds(ts: str) -> float:
    """Convert SRT timestamp (HH:MM:SS,mmm) to seconds."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def generate_subtitle_overlay(subs: list, width: int, height: int, duration: float, fps: int) -> str:
    """Generate a transparent video with subtitle text using Pillow, encoded as VP9+alpha."""
    from PIL import Image, ImageDraw, ImageFont
    import tempfile

    total_frames = int(duration * fps)
    frame_dir = tempfile.mkdtemp(prefix="subs_")

    # Try to load a good font
    font = None
    for font_path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, 36)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    print(f"  Rendering {total_frames} subtitle overlay frames...")

    for frame_num in range(total_frames):
        t = frame_num / fps

        # Find active subtitle
        active_text = None
        for sub in subs:
            if sub["start"] <= t < sub["end"]:
                active_text = sub["text"]
                break

        # Create transparent frame
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        if active_text:
            draw = ImageDraw.Draw(img)

            # Word-wrap text to fit width
            max_chars = 40
            words = active_text.split()
            lines = []
            current_line = ""
            for word in words:
                test = f"{current_line} {word}".strip()
                if len(test) > max_chars and current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    current_line = test
            if current_line:
                lines.append(current_line)

            # Draw semi-transparent background box + white text
            line_height = 44
            padding = 16
            total_text_h = len(lines) * line_height
            box_y = height - 240 - padding
            box_h = total_text_h + padding * 2

            # Background box
            draw.rounded_rectangle(
                [(40, box_y), (width - 40, box_y + box_h)],
                radius=12,
                fill=(0, 0, 0, 160),
            )

            # Text lines
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                text_w = bbox[2] - bbox[0]
                x = (width - text_w) // 2
                y = box_y + padding + i * line_height
                draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

        img.save(f"{frame_dir}/frame_{frame_num:05d}.png")

    # Encode transparent frames as video using PNG sequence
    fd, overlay_path = tempfile.mkstemp(prefix="subtitle_overlay_", suffix=".mov")
    os.close(fd)
    encode_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", f"{frame_dir}/frame_%05d.png",
        "-c:v", "png",
        "-pix_fmt", "rgba",
        overlay_path,
    ]
    result = subprocess.run(encode_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Overlay encoding error: {result.stderr[-300:]}")

    # Clean up frame PNGs
    import glob as glob_mod
    for f in glob_mod.glob(f"{frame_dir}/frame_*.png"):
        os.remove(f)
    os.rmdir(frame_dir)

    return overlay_path


def create_video(
    manifest_path: str,
    audio_path: str | None = None,
    script_path: str | None = None,
    logo_path: str | None = None,
    bg_music_path: str | None = None,
    output_suffix: str = "",
    durations_path: str | None = None,
    branding_logo_path: str | None = None,
):
    import shutil
    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg not found. Install with: brew install ffmpeg")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    frames = manifest["frames"]
    if not frames:
        print("Error: No frames found in manifest")
        return None

    # Override frame durations with actual audio-measured durations if available
    if durations_path and os.path.exists(durations_path):
        with open(durations_path) as f:
            dur_data = json.load(f)
        dur_map = {d["scene_number"]: d["duration"] for d in dur_data}
        for frame in frames:
            if frame["scene"] in dur_map:
                frame["duration"] = dur_map[frame["scene"]]
        print(f"  Using audio-synced durations from {durations_path}")

    base_name = os.path.splitext(os.path.basename(manifest_path))[0].replace("_frames", "")
    out_path = f"output/{base_name}{output_suffix}_video.mp4"

    crossfade_duration = 0.0
    total_duration = sum(f["duration"] for f in frames) - crossfade_duration * (len(frames) - 1)

    # Subtitles disabled — they didn't land well in the video
    srt_path = None

    # --- PASS 1: Build video with crossfades + logo + audio ---
    # (Subtitles are burned in pass 2 to avoid FFmpeg escaping issues)
    cmd = ["ffmpeg", "-y"]

    # Input: frame images
    for frame in frames:
        cmd.extend(["-loop", "1", "-t", str(frame["duration"]), "-i", frame["path"]])

    input_idx = len(frames)

    # Input: voiceover
    vo_idx = None
    if audio_path:
        cmd.extend(["-i", audio_path])
        vo_idx = input_idx
        input_idx += 1

    # Input: background music
    bg_idx = None
    if bg_music_path and os.path.exists(bg_music_path):
        cmd.extend(["-stream_loop", "-1", "-i", bg_music_path])
        bg_idx = input_idx
        input_idx += 1

    # Input: company logo (top-right)
    logo_idx = None
    if logo_path and os.path.exists(logo_path):
        cmd.extend(["-i", logo_path])
        logo_idx = input_idx
        input_idx += 1

    # Input: branding logo (bottom-right)
    branding_idx = None
    if branding_logo_path and os.path.exists(branding_logo_path):
        cmd.extend(["-i", branding_logo_path])
        branding_idx = input_idx
        input_idx += 1

    # --- Build filter complex ---
    filter_parts = []

    # Scale all frame inputs
    for i in range(len(frames)):
        filter_parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]"
        )

    # Chain frames together
    if len(frames) == 1:
        prev = "v0"
    elif crossfade_duration <= 0:
        # No crossfade — simple concat
        concat_inputs = "".join(f"[v{i}]" for i in range(len(frames)))
        filter_parts.append(
            f"{concat_inputs}concat=n={len(frames)}:v=1:a=0[concatv]"
        )
        prev = "concatv"
    else:
        prev = "v0"
        offset = frames[0]["duration"] - crossfade_duration
        for i in range(1, len(frames)):
            out_label = f"xf{i}"
            filter_parts.append(
                f"[{prev}][v{i}]xfade=transition=fade:duration={crossfade_duration}:offset={offset}[{out_label}]"
            )
            prev = out_label
            if i < len(frames) - 1:
                offset += frames[i]["duration"] - crossfade_duration

    video_label = prev

    # Overlay company logo (top-right corner)
    if logo_idx is not None:
        cw = _stitch_cfg.get("company_logo_width", 220)
        co = _stitch_cfg.get("company_logo_opacity", 0.8)
        filter_parts.append(
            f"[{logo_idx}:v]scale={cw}:-1,format=rgba,colorchannelmixer=aa={co}[clogo]"
        )
        filter_parts.append(
            f"[{video_label}][clogo]overlay=W-w-40:40[with_clogo]"
        )
        video_label = "with_clogo"

    # Overlay SwishX branding logo (bottom-right, above subtitle area)
    if branding_idx is not None:
        bw = _stitch_cfg.get("branding_logo_width", 120)
        bo = _stitch_cfg.get("branding_logo_opacity", 0.6)
        filter_parts.append(
            f"[{branding_idx}:v]scale={bw}:-1,format=rgba,colorchannelmixer=aa={bo}[blogo]"
        )
        filter_parts.append(
            f"[{video_label}][blogo]overlay=W-w-30:H-h-30[with_blogo]"
        )
        video_label = "with_blogo"

    # Final video output label
    filter_parts.append(f"[{video_label}]copy[vout]")

    # Audio mixing: voiceover (loud) + background music (quiet)
    audio_filter_parts = []
    if vo_idx is not None and bg_idx is not None:
        audio_filter_parts.append(
            f"[{vo_idx}:a]volume=1.0[vo];"
            f"[{bg_idx}:a]volume=0.08,afade=t=in:st=0:d=2,afade=t=out:st={total_duration-3}:d=3[bg];"
            f"[vo][bg]amix=inputs=2:duration=shortest:dropout_transition=2[aout]"
        )
    elif vo_idx is not None:
        audio_filter_parts.append(f"[{vo_idx}:a]acopy[aout]")
    elif bg_idx is not None:
        audio_filter_parts.append(
            f"[{bg_idx}:a]volume=0.15,afade=t=in:st=0:d=2,afade=t=out:st={total_duration-3}:d=3[aout]"
        )

    # Combine video and audio filters
    full_filter = ";".join(filter_parts)
    if audio_filter_parts:
        full_filter += ";" + ";".join(audio_filter_parts)

    cmd.extend(["-filter_complex", full_filter])
    cmd.extend(["-map", "[vout]"])

    if audio_filter_parts:
        cmd.extend(["-map", "[aout]"])

    encoder_args = _get_encoder_args()
    fps = _stitch_cfg.get("frame_rate", 24)
    cmd.extend(encoder_args + [
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-shortest",
    ])

    if audio_filter_parts:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    # If no subtitles, output directly to final path; otherwise use temp file
    pass1_path = out_path if not srt_path else f"output/{base_name}{output_suffix}_tmp.mp4"
    cmd.append(pass1_path)

    print(f"\nStitching {len(frames)} frames into video...")
    print(f"  Resolution: 1080x1920 (9:16)")
    print(f"  Company logo: {'yes' if logo_idx else 'no'}")
    print(f"  Branding logo: {'yes' if branding_idx else 'no'}")
    print(f"  Subtitles: {'yes' if srt_path else 'no'}")
    print(f"  Voiceover: {'yes' if vo_idx else 'no'}")
    print(f"  Background music: {'yes' if bg_idx else 'no'}")
    print(f"  Transitions: {crossfade_duration}s crossfade")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg pass 1 error:\n{result.stderr[-2000:]}")
        return None

    # --- PASS 2: Burn in subtitles using Pillow + FFmpeg overlay ---
    # FFmpeg's subtitles/drawtext filters require libass/libfreetype (not in brew build).
    # Instead: generate transparent subtitle overlay video with Pillow, then overlay in FFmpeg.
    if srt_path:
        import shutil
        subs = parse_srt(srt_path)

        if subs:
            print("Burning subtitles (pass 2)...")
            overlay_path = generate_subtitle_overlay(subs, 1080, 1920, total_duration, 30)

            sub_cmd = [
                "ffmpeg", "-y",
                "-i", pass1_path,
                "-i", overlay_path,
                "-filter_complex", "[1:v]format=argb[sub];[0:v][sub]overlay=0:0:shortest=1[vout]",
                "-map", "[vout]",
                "-map", "0:a?",
            ] + _get_encoder_args() + [
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                out_path,
            ]

            result = subprocess.run(sub_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFmpeg pass 2 (subtitles) error:\n{result.stderr[-500:]}")
                print("Falling back to video without subtitles.")
                shutil.move(pass1_path, out_path)
            else:
                os.remove(pass1_path)
                os.remove(overlay_path)
        else:
            shutil.move(pass1_path, out_path)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"Video created: {out_path}")
    print(f"  Duration: ~{total_duration:.1f}s")
    print(f"  Size: {size_mb:.1f} MB")
    return out_path


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python step4_stitch_video.py <frames_manifest.json> [voiceover.mp3] [script.json] [--logo path] [--music path] [--suffix text]"
        )
        sys.exit(1)

    manifest_path = sys.argv[1]
    audio_path = None
    script_path = None
    logo_path = DEFAULT_LOGO
    branding_logo_path = BRANDING_LOGO
    bg_music_path = DEFAULT_BG_MUSIC
    output_suffix = ""
    durations_path = None

    # Parse args
    i = 2
    positional = 0
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--logo":
            logo_path = sys.argv[i + 1]
            i += 2
        elif arg == "--branding-logo":
            branding_logo_path = sys.argv[i + 1]
            i += 2
        elif arg == "--music":
            bg_music_path = sys.argv[i + 1]
            i += 2
        elif arg == "--no-music":
            bg_music_path = None
            i += 1
        elif arg == "--no-logo":
            logo_path = None
            i += 1
        elif arg == "--no-branding":
            branding_logo_path = None
            i += 1
        elif arg == "--suffix":
            output_suffix = sys.argv[i + 1]
            i += 2
        elif arg == "--durations":
            durations_path = sys.argv[i + 1]
            i += 2
        else:
            if positional == 0:
                audio_path = arg
            elif positional == 1:
                script_path = arg
            positional += 1
            i += 1

    create_video(manifest_path, audio_path, script_path, logo_path, bg_music_path, output_suffix, durations_path, branding_logo_path)


if __name__ == "__main__":
    main()
