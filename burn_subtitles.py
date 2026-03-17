"""
Burn phrase-based subtitles onto an existing video.

Uses the script JSON + durations JSON to calculate exact timing per scene,
splits narrations into short phrases, and renders them via Pillow + FFmpeg overlay.

Usage:
  python burn_subtitles.py <video.mp4> <script.json> <durations.json>

Outputs:
  <video>_subtitled.mp4
"""

import json
import sys
import os
import platform
import tempfile
import subprocess
from PIL import Image, ImageDraw, ImageFont


# --- Font fallback chain ---
FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",              # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux (Docker)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _find_font():
    for p in FONT_PATHS:
        if os.path.exists(p):
            return p
    return None


def _is_macos():
    return platform.system() == "Darwin"


def _get_encoder_args():
    """Return FFmpeg encoder args: videotoolbox on mac, libx264 fast on linux."""
    if _is_macos():
        # Check if videotoolbox is available
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=5,
            )
            if "h264_videotoolbox" in result.stdout:
                return ["-c:v", "h264_videotoolbox", "-q:v", "65"]
        except Exception:
            pass
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]


# --- Style config (doctor profile) ---
STYLE = {
    "font_path": _find_font() or "/System/Library/Fonts/Helvetica.ttc",
    "font_size": 40,
    "bold_font_size": 42,
    "text_color": (255, 255, 255, 255),          # white
    "highlight_color": (0, 210, 211, 255),        # teal for drug names
    "bg_color": (0, 0, 0, 160),                   # semi-transparent black box
    "bg_radius": 16,
    "bg_padding_x": 32,
    "bg_padding_y": 20,
    "position_y_pct": 0.93,                       # 93% from top (very bottom)
    "max_words_per_phrase": 5,
    "line_height": 48,
}

# Base drug/pharma terms to highlight in teal (extended dynamically from script JSON)
DRUG_NAMES = {
    "allerduo", "bilastine", "montelukast",
    "h1", "cyslt1", "histamine", "leukotriene", "leukotrienes",
    "tibrolin", "trypsin", "bromelain", "rutoside", "rutoxide",
    "subneuro", "nortriptyline", "pregabalin", "methylcobalamin",
    "mg", "mcg",
}


def enrich_drug_names(script):
    """Add product_name and composition words to DRUG_NAMES for teal highlighting."""
    for key in ("product_name", "composition"):
        val = script.get(key, "")
        if val:
            for word in val.replace("+", " ").replace(",", " ").split():
                cleaned = word.strip("()").lower()
                if len(cleaned) > 2:
                    DRUG_NAMES.add(cleaned)

CROSSFADE = 0.0  # must match what step4_stitch_video uses
WIDTH = 1080
HEIGHT = 1920
FPS = 30


def split_into_phrases(text, max_words=5):
    """Split narration into short phrases at natural break points."""
    words = text.split()
    phrases = []
    current = []

    for word in words:
        current.append(word)
        # Break at punctuation or when max words reached
        if (len(current) >= max_words or
            word[-1] in ".,;:!?" or
            (len(current) >= 3 and word[-1] == "-")):
            phrases.append(" ".join(current))
            current = []

    if current:
        phrases.append(" ".join(current))

    return phrases


def calculate_scene_starts(durations):
    """Calculate the exact start time of each scene in the video, accounting for crossfade."""
    starts = []
    current_time = 0.0
    for i, d in enumerate(durations):
        starts.append(current_time)
        if i < len(durations) - 1:
            current_time += d["duration"] - CROSSFADE
    return starts


def build_subtitle_events(script, durations):
    """Build a list of {start, end, text, has_highlight} subtitle events."""
    scene_starts = calculate_scene_starts(durations)
    events = []

    for i, scene in enumerate(script["scenes"]):
        scene_type = scene.get("scene_type", "content")

        # Skip silent scenes (quiz, quiz_answer, leaderboard) — no subtitles
        if scene_type in ("quiz", "quiz_answer", "leaderboard"):
            continue

        narration = scene.get("narration", "").strip()
        if not narration:
            continue

        scene_start = scene_starts[i]
        scene_duration = durations[i]["duration"]

        # Split into phrases
        phrases = split_into_phrases(narration, STYLE["max_words_per_phrase"])
        if not phrases:
            continue

        # Distribute time evenly across phrases, with small gaps
        gap = 0.15  # gap between phrases
        total_gap = gap * (len(phrases) - 1) if len(phrases) > 1 else 0
        available = scene_duration - 0.5 - total_gap  # 0.5s buffer at end
        phrase_duration = max(available / len(phrases), 0.8)

        t = scene_start + 0.2  # small delay at scene start
        for phrase in phrases:
            events.append({
                "start": t,
                "end": t + phrase_duration,
                "text": phrase,
            })
            t += phrase_duration + gap

    return events


def build_box_ranges(script, durations):
    """Build time ranges where the subtitle box should be visible (narrated scenes)."""
    scene_starts = calculate_scene_starts(durations)
    ranges = []

    for i, scene in enumerate(script["scenes"]):
        scene_type = scene.get("scene_type", "content")
        if scene_type in ("quiz", "quiz_answer", "leaderboard"):
            continue
        narration = scene.get("narration", "").strip()
        if not narration:
            continue

        scene_start = scene_starts[i]
        scene_end = scene_start + durations[i]["duration"]
        ranges.append((scene_start, scene_end))

    return ranges


def is_in_box_range(t, box_ranges):
    """Check if time t falls within any narrated scene range."""
    for start, end in box_ranges:
        if start <= t < end:
            return True
    return False


def is_highlight_word(word):
    """Check if a word should be highlighted (drug name, clinical term)."""
    clean = word.lower().strip(".,;:!?()-\"'")
    return clean in DRUG_NAMES


def get_fixed_box_dims(width, height):
    """Return fixed box position and size (2 lines tall, full width)."""
    line_h = STYLE["line_height"]
    max_w = width - STYLE["bg_padding_x"] * 2 - 80
    box_w = min(max_w + STYLE["bg_padding_x"] * 2, width - 60)
    box_h = 1 * line_h + STYLE["bg_padding_y"] * 2  # single-line height
    box_x = (width - box_w) // 2
    box_y = int(height * STYLE["position_y_pct"]) - box_h // 2
    return box_x, box_y, box_w, box_h


def render_subtitle_box(draw, width, height):
    """Render just the fixed background box (no text)."""
    box_x, box_y, box_w, box_h = get_fixed_box_dims(width, height)
    draw.rounded_rectangle(
        [(box_x, box_y), (box_x + box_w, box_y + box_h)],
        radius=STYLE["bg_radius"],
        fill=STYLE["bg_color"],
    )


def render_subtitle_text(draw, text, width, height, font, bold_font):
    """Render text inside the fixed box."""
    box_x, box_y, box_w, box_h = get_fixed_box_dims(width, height)

    words = text.split()
    space_w = draw.textlength(" ", font=font)
    word_infos = []
    for word in words:
        f = bold_font if is_highlight_word(word) else font
        w = draw.textlength(word, font=f)
        word_infos.append({"word": word, "width": w, "font": f, "highlight": is_highlight_word(word)})

    # Word wrap
    max_w = box_w - STYLE["bg_padding_x"] * 2
    lines = []
    current_line = []
    current_w = 0
    for info in word_infos:
        test_w = current_w + info["width"] + (space_w if current_line else 0)
        if test_w > max_w and current_line:
            lines.append(current_line)
            current_line = [info]
            current_w = info["width"]
        else:
            current_line.append(info)
            current_w = test_w
    if current_line:
        lines.append(current_line)

    # Vertically center text within box
    line_h = STYLE["line_height"]
    text_h = len(lines) * line_h
    y = box_y + (box_h - text_h) // 2

    for line in lines:
        line_w = sum(info["width"] for info in line) + space_w * (len(line) - 1)
        x = (width - line_w) // 2
        for info in line:
            color = STYLE["highlight_color"] if info["highlight"] else STYLE["text_color"]
            draw.text((x, y), info["word"], font=info["font"], fill=color)
            x += info["width"] + space_w
        y += line_h


def _generate_overlay_video_legacy(events, duration, output_path, box_ranges=None):
    """Legacy: render every frame individually. Kept as fallback."""
    total_frames = int(duration * FPS)
    frame_dir = tempfile.mkdtemp(prefix="subs_")

    try:
        font = ImageFont.truetype(STYLE["font_path"], STYLE["font_size"])
        bold_font = ImageFont.truetype(STYLE["font_path"], STYLE["bold_font_size"])
    except (OSError, IOError):
        font = ImageFont.load_default()
        bold_font = font

    print(f"  [legacy] Rendering {total_frames} subtitle frames ({duration:.1f}s at {FPS}fps)...")

    for frame_num in range(total_frames):
        t = frame_num / FPS
        active_event = None
        for ev in events:
            if ev["start"] <= t < ev["end"]:
                active_event = ev
                break

        img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        show_box = box_ranges and is_in_box_range(t, box_ranges)
        if show_box:
            draw = ImageDraw.Draw(img)
            render_subtitle_box(draw, WIDTH, HEIGHT)
            if active_event:
                render_subtitle_text(draw, active_event["text"], WIDTH, HEIGHT, font, bold_font)

        img.save(f"{frame_dir}/frame_{frame_num:05d}.png")
        if frame_num % (FPS * 5) == 0:
            print(f"    {frame_num}/{total_frames} frames ({t:.1f}s)")

    print(f"  Encoding overlay video...")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", f"{frame_dir}/frame_%05d.png",
        "-c:v", "png", "-pix_fmt", "rgba",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Encode error: {result.stderr[-500:]}")
        return None

    import glob as g
    for f in g.glob(f"{frame_dir}/frame_*.png"):
        os.remove(f)
    os.rmdir(frame_dir)
    return output_path


def generate_overlay_video(events, duration, output_path, box_ranges=None):
    """Fast: render only unique visual states, use FFmpeg concat demuxer."""
    try:
        font = ImageFont.truetype(STYLE["font_path"], STYLE["font_size"])
        bold_font = ImageFont.truetype(STYLE["font_path"], STYLE["bold_font_size"])
    except (OSError, IOError):
        font = ImageFont.load_default()
        bold_font = font

    # Build timeline of visual states: (start_time, end_time, state_key)
    # States: "empty", "box_only", "box_text:<phrase>"
    timeline = []
    all_times = sorted(set(
        [0.0, duration]
        + [ev["start"] for ev in events]
        + [ev["end"] for ev in events]
        + [r[0] for r in (box_ranges or [])]
        + [r[1] for r in (box_ranges or [])]
    ))

    for i in range(len(all_times) - 1):
        t_start = all_times[i]
        t_end = all_times[i + 1]
        if t_end - t_start < 0.001:
            continue

        t_mid = (t_start + t_end) / 2
        show_box = box_ranges and is_in_box_range(t_mid, box_ranges)
        active_text = None
        for ev in events:
            if ev["start"] <= t_mid < ev["end"]:
                active_text = ev["text"]
                break

        if show_box and active_text:
            state_key = f"box_text:{active_text}"
        elif show_box:
            state_key = "box_only"
        else:
            state_key = "empty"

        timeline.append((t_start, t_end, state_key))

    # Merge consecutive segments with the same state
    merged = []
    for seg in timeline:
        if merged and merged[-1][2] == seg[2]:
            merged[-1] = (merged[-1][0], seg[1], seg[2])
        else:
            merged.append(list(seg))

    # Render unique states
    unique_states = set(seg[2] for seg in merged)
    frame_dir = tempfile.mkdtemp(prefix="subs_fast_")
    state_files = {}

    print(f"  Rendering {len(unique_states)} unique subtitle states (was ~{int(duration * FPS)} frames)...")

    for state_key in unique_states:
        img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        if state_key == "box_only":
            draw = ImageDraw.Draw(img)
            render_subtitle_box(draw, WIDTH, HEIGHT)
        elif state_key.startswith("box_text:"):
            text = state_key[len("box_text:"):]
            draw = ImageDraw.Draw(img)
            render_subtitle_box(draw, WIDTH, HEIGHT)
            render_subtitle_text(draw, text, WIDTH, HEIGHT, font, bold_font)
        # "empty" stays transparent

        safe_name = f"state_{abs(hash(state_key)):016x}.png"
        path = os.path.join(frame_dir, safe_name)
        img.save(path)
        state_files[state_key] = path

    # Write FFmpeg concat file
    concat_path = os.path.join(frame_dir, "concat.txt")
    with open(concat_path, "w") as f:
        for seg_start, seg_end, state_key in merged:
            seg_duration = seg_end - seg_start
            f.write(f"file '{state_files[state_key]}'\n")
            f.write(f"duration {seg_duration:.6f}\n")
        # FFmpeg concat needs the last file repeated without duration
        if merged:
            f.write(f"file '{state_files[merged[-1][2]]}'\n")

    print(f"  Encoding overlay via concat demuxer ({len(merged)} segments)...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_path,
        "-c:v", "png", "-pix_fmt", "rgba",
        "-r", str(FPS),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Fast overlay failed: {result.stderr[-500:]}")
        print(f"  Falling back to legacy renderer...")
        # Clean up and fall back
        import glob as g
        for f_path in g.glob(f"{frame_dir}/*"):
            os.remove(f_path)
        os.rmdir(frame_dir)
        return _generate_overlay_video_legacy(events, duration, output_path, box_ranges)

    # Clean up
    import glob as g
    for f_path in g.glob(f"{frame_dir}/*"):
        os.remove(f_path)
    os.rmdir(frame_dir)
    return output_path


def burn_onto_video(video_path, overlay_path, output_path):
    """Composite subtitle overlay onto video using platform-aware encoder."""
    encoder_args = _get_encoder_args()
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", overlay_path,
        "-filter_complex", "[1:v]format=argb[sub];[0:v][sub]overlay=0:0:shortest=1[vout]",
        "-map", "[vout]",
        "-map", "0:a?",
    ] + encoder_args + [
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]
    encoder_name = encoder_args[1]  # e.g. "h264_videotoolbox" or "libx264"
    print(f"  Compositing subtitles onto video ({encoder_name})...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Error: {result.stderr[-500:]}")
        return None
    return output_path


def main():
    import shutil
    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg not found. Install with: brew install ffmpeg")
        sys.exit(1)

    if len(sys.argv) < 4:
        print("Usage: python burn_subtitles.py <video.mp4> <script.json> <durations.json>")
        sys.exit(1)

    video_path = sys.argv[1]
    script_path = sys.argv[2]
    durations_path = sys.argv[3]

    with open(script_path) as f:
        script = json.load(f)
    with open(durations_path) as f:
        durations = json.load(f)

    # Enrich highlight words from this specific drug's script
    enrich_drug_names(script)

    # Get video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    video_duration = float(probe.stdout.strip())

    print(f"Video: {video_path} ({video_duration:.1f}s)")
    print(f"Script: {len(script['scenes'])} scenes")
    print(f"Style: Doctor (clean phrase-based, teal drug name highlights)")

    # Build subtitle events and box ranges
    events = build_subtitle_events(script, durations)
    box_ranges = build_box_ranges(script, durations)
    print(f"\nGenerated {len(events)} subtitle phrases:")
    for ev in events:
        highlight_words = [w for w in ev["text"].split() if is_highlight_word(w)]
        marker = " [teal]" if highlight_words else ""
        print(f"  {ev['start']:6.2f}s - {ev['end']:6.2f}s  \"{ev['text']}\"{marker}")

    # Generate overlay
    fd, overlay_path = tempfile.mkstemp(prefix="subtitle_overlay_", suffix=".mov")
    os.close(fd)
    print(f"\nRendering subtitle overlay...")
    result = generate_overlay_video(events, video_duration, overlay_path, box_ranges)
    if not result:
        print("Failed to generate overlay")
        sys.exit(1)

    # Burn onto video
    base = os.path.splitext(video_path)[0]
    output_path = f"{base}_subtitled.mp4"
    result = burn_onto_video(video_path, overlay_path, output_path)

    if result:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"\nDone: {output_path} ({size_mb:.1f} MB)")
        # Cleanup overlay
        os.remove(overlay_path)
    else:
        print("Failed to burn subtitles")
        sys.exit(1)


if __name__ == "__main__":
    main()
