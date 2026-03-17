"""
Step 3: Generate video frames per scene.

- Structured scenes (quiz, quiz_intro, quiz_answer, score, cta, leaderboard)
  are rendered with Pillow templates for pixel-perfect reliability.
- Content scenes use AI image generation (Gemini) with retry + Pillow fallback.

Prerequisites:
  - Set env var: GOOGLE_API_KEY
"""

from __future__ import annotations
import json
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from frame_templates import TEMPLATE_RENDERERS, render_content_fallback
from config_loader import load_models, load_frame_style_base, load_frame_text_guard

_models = load_models()
_frame_cfg = _models["frame_generation"]

MODEL = _frame_cfg["model"]
MAX_RETRIES = _frame_cfg["max_retries"]
RETRY_DELAY = _frame_cfg["retry_delay_seconds"]

STYLE_BASE = load_frame_style_base()


def render_leaderboard(scene: dict, filename: str) -> str | None:
    """Render leaderboard with Pillow for precise table layout."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    img = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        r = int(30 + (70 - 30) * y / H)
        g = int(60 + (160 - 60) * y / H)
        b = int(180 + (240 - 180) * y / H)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    draw = ImageDraw.Draw(img)

    _font_paths = [
        '/System/Library/Fonts/Helvetica.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    _fp = None
    for p in _font_paths:
        if os.path.exists(p):
            _fp = p
            break

    try:
        font_bold = ImageFont.truetype(_fp, 52) if _fp else ImageFont.load_default()
        font_header = ImageFont.truetype(_fp, 32) if _fp else ImageFont.load_default()
        font_row = ImageFont.truetype(_fp, 38) if _fp else ImageFont.load_default()
        font_row_small = ImageFont.truetype(_fp, 34) if _fp else ImageFont.load_default()
        font_you = ImageFont.truetype(_fp, 40) if _fp else ImageFont.load_default()
    except (OSError, IOError):
        font_bold = font_header = font_row = font_row_small = font_you = ImageFont.load_default()

    title = 'LEADERBOARD'
    bbox = draw.textbbox((0, 0), title, font=font_bold)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 280), title, fill='white', font=font_bold)
    draw.ellipse([(W//2 - 30, 210), (W//2 + 30, 270)], fill=(255, 215, 0))
    draw.text((W//2 - 12, 220), '\u2605', fill='white', font=font_header)

    header_y = 380
    col_rank_x, col_name_x, col_state_x, col_xp_x = 100, 200, 550, 820
    draw.text((col_rank_x, header_y), 'RANK', fill=(200, 200, 255), font=font_header)
    draw.text((col_name_x, header_y), 'NAME', fill=(200, 200, 255), font=font_header)
    draw.text((col_state_x, header_y), 'STATE', fill=(200, 200, 255), font=font_header)
    draw.text((col_xp_x, header_y), 'XP', fill=(200, 200, 255), font=font_header)
    draw.line([(80, header_y + 50), (W - 80, header_y + 50)], fill=(255, 255, 255), width=2)

    lb = scene.get("leaderboard", [])
    defaults = [
        {"rank": 1, "name": "Anurag", "state": "Maharashtra", "xp": 2850},
        {"rank": 2, "name": "Jai", "state": "Delhi", "xp": 2640},
        {"rank": 3, "name": "Dushyant", "state": "Karnataka", "xp": 2420},
        {"rank": 4, "name": "You", "state": "Gujarat", "xp": 2100},
        {"rank": 5, "name": "Vikas", "state": "Rajasthan", "xp": 1980},
    ]
    entries = lb if len(lb) >= 5 else defaults
    medals = [(255, 215, 0), (192, 192, 192), (205, 127, 50), None, None]

    row_height = 120
    start_y = header_y + 70
    card_margin = 60

    for i, entry in enumerate(entries):
        y = start_y + i * row_height
        is_you = entry.get("name", "") == "You"
        medal = medals[i] if i < len(medals) else None
        text_color = 'white' if is_you else (40, 40, 80)

        if is_you:
            draw.rounded_rectangle([(card_margin, y), (W - card_margin, y + row_height - 15)], radius=20, fill=(255, 140, 0))
        else:
            draw.rounded_rectangle([(card_margin, y), (W - card_margin, y + row_height - 15)], radius=20, fill=(255, 255, 255))

        text_y = y + 22
        rank = entry.get("rank", i + 1)

        if medal:
            cx, cy = col_rank_x + 10, text_y + 15
            draw.ellipse([(cx - 18, cy - 18), (cx + 18, cy + 18)], fill=medal)
            rs = str(rank)
            rb = draw.textbbox((0, 0), rs, font=font_row_small)
            draw.text((cx - (rb[2]-rb[0])//2, cy - (rb[3]-rb[1])//2 - 2), rs, fill='white', font=font_row_small)
        else:
            draw.text((col_rank_x, text_y), str(rank), fill=text_color, font=font_row)

        draw.text((col_name_x, text_y), entry.get("name", ""), fill=text_color, font=font_you if is_you else font_row)

        if is_you:
            badge_x = col_name_x + 100
            draw.rounded_rectangle([(badge_x, text_y + 2), (badge_x + 65, text_y + 35)], radius=10, fill='white')
            draw.text((badge_x + 8, text_y + 4), 'YOU', fill=(255, 140, 0), font=font_header)

        draw.text((col_state_x, text_y), entry.get("state", ""), fill=text_color, font=font_row_small)
        draw.text((col_xp_x, text_y), str(entry.get("xp", "")), fill=text_color, font=font_row)

    img.save(filename)
    size = os.path.getsize(filename)
    print(f"    Rendered leaderboard ({size/1024:.0f} KB)")
    return filename


def generate_frame_ai(client, prompt: str, filename: str) -> str | None:
    """Generate one frame using AI with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16",
                    ),
                ),
            )

            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    image.save(filename)
                    size = os.path.getsize(filename)
                    print(f"    Saved ({size/1024:.0f} KB)")
                    return filename

            print(f"    No image in response (attempt {attempt}/{MAX_RETRIES})")

        except Exception as e:
            print(f"    Error (attempt {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    return None


def build_content_prompt(scene: dict) -> str:
    """Build AI prompt for content scenes.

    Adds a strong instruction to minimize text rendering in the image,
    since AI image generators often garble multi-word text.
    """
    image_prompt = scene.get("image_prompt", "")

    # Add text-avoidance instruction to all AI prompts
    text_guard = load_frame_text_guard()

    if image_prompt:
        return STYLE_BASE + text_guard + image_prompt

    on_screen = scene.get("on_screen_text", [])
    key_text = on_screen[0] if on_screen else ""
    return (
        STYLE_BASE
        + text_guard
        + f"Center: bold white text '{key_text}'. "
        + "Clean pharmaceutical information frame with relevant medical icons."
    )


def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: Set GOOGLE_API_KEY env var")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python step3_generate_frames.py <script.json>")
        sys.exit(1)

    script_path = sys.argv[1]
    with open(script_path) as f:
        script = json.load(f)

    product_name = script["product_name"]
    scenes = script["scenes"]

    base_name = os.path.splitext(os.path.basename(script_path))[0]
    frames_dir = f"output/{base_name}_frames"
    os.makedirs(frames_dir, exist_ok=True)

    client = genai.Client(api_key=api_key)

    print(f"Generating {len(scenes)} frames for {product_name}")
    print(f"  Content scenes: AI ({MODEL}) with Pillow fallback")
    print(f"  Structured scenes: Pillow templates\n")

    frame_paths = []
    errors = []

    # Separate scenes into template (Pillow, instant) and AI (Gemini, slow)
    template_scenes = []
    ai_scenes = []
    for scene in scenes:
        scene_type = scene.get("scene_type", "content")
        scene_num = scene["scene_number"]
        filename = f"{frames_dir}/scene_{scene_num:02d}_{scene_type}.png"
        if scene_type in ("leaderboard",) or scene_type in TEMPLATE_RENDERERS:
            template_scenes.append((scene, filename))
        elif scene_type == "content":
            ai_scenes.append((scene, filename))
        else:
            template_scenes.append((scene, filename))

    # Render template scenes (instant, no API calls)
    results = {}  # scene_num -> (path, error_info)
    for scene, filename in template_scenes:
        scene_type = scene.get("scene_type", "content")
        scene_num = scene["scene_number"]
        label = scene["on_screen_text"][0] if scene.get("on_screen_text") else scene_type
        print(f"Scene {scene_num} [{scene_type}]: {label}")

        if scene_type == "leaderboard":
            path = render_leaderboard(scene, filename)
        elif scene_type in TEMPLATE_RENDERERS:
            path = TEMPLATE_RENDERERS[scene_type](scene, filename)
            if path:
                size = os.path.getsize(filename)
                print(f"    Rendered template ({size/1024:.0f} KB)")
        else:
            print(f"    Unknown scene type '{scene_type}', using fallback")
            path = render_content_fallback(scene, filename)
        results[scene_num] = (path, None)

    # Generate AI frames in parallel
    def _generate_one_frame(scene, filename):
        scene_num = scene["scene_number"]
        prompt = build_content_prompt(scene)
        path = generate_frame_ai(client, prompt, filename)
        if path is None:
            path = render_content_fallback(scene, filename)
            return scene_num, path, {"scene": scene_num, "type": "content",
                                     "error": "AI generation failed, used Pillow fallback"}
        return scene_num, path, None

    if ai_scenes:
        max_workers = min(len(ai_scenes), 4)  # cap at 4 to avoid rate limits
        print(f"\nGenerating {len(ai_scenes)} AI frames in parallel (max {max_workers} workers)...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_generate_one_frame, scene, filename): scene
                       for scene, filename in ai_scenes}
            for future in as_completed(futures):
                scene = futures[future]
                scene_num = scene["scene_number"]
                label = scene["on_screen_text"][0] if scene.get("on_screen_text") else "content"
                try:
                    sn, path, err_info = future.result()
                    status = "OK" if err_info is None else "fallback"
                    print(f"  Scene {sn} [{status}]: {label}")
                    results[sn] = (path, err_info)
                except Exception as e:
                    print(f"  Scene {scene_num} [ERROR]: {e}")
                    path = render_content_fallback(scene, filename)
                    results[scene_num] = (path, {"scene": scene_num, "type": "content", "error": str(e)})

    # Assemble frame_paths in scene order
    for scene in scenes:
        scene_num = scene["scene_number"]
        scene_type = scene.get("scene_type", "content")
        path, err_info = results.get(scene_num, (None, None))
        if err_info:
            errors.append(err_info)
        if path:
            frame_paths.append({
                "scene": scene_num,
                "scene_type": scene_type,
                "path": path,
                "duration": scene["duration_seconds"],
            })

    # Save frame manifest
    manifest_path = f"output/{base_name}_frames.json"
    manifest = {
        "product_name": product_name,
        "script_path": script_path,
        "frames": frame_paths,
    }
    if errors:
        manifest["errors"] = errors

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'='*50}")
    print(f"Generated {len(frame_paths)}/{len(scenes)} frames")
    if errors:
        print(f"  {len(errors)} used Pillow fallback (AI failed)")
    print(f"Frames dir: {frames_dir}/")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
