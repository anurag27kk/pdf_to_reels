"""
Pillow-based frame templates for structured scene types.

These render pixel-perfect frames without relying on AI image generation.
Used as the primary renderer for: quiz_intro, quiz, quiz_answer, score, cta.
Used as fallback for content scenes when AI generation fails.

All frames are 1080x1920 (9:16 vertical mobile reel).
"""

from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1080, 1920


_FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

_DEVANAGARI_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",  # macOS
    "/System/Library/Fonts/Kohinoor.ttc",                            # macOS alt
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", # Linux (fonts-noto)
    "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.otf", # Linux alt
]


def _find_system_font(language: str = "en"):
    if language == "hi":
        for p in _DEVANAGARI_FONT_PATHS:
            if os.path.exists(p):
                return p
    for p in _FONT_PATHS:
        if os.path.exists(p):
            return p
    return None


def _load_fonts(sizes: dict[str, int], language: str = "en") -> dict[str, ImageFont.FreeTypeFont]:
    """Load fonts at specified sizes. Falls back to default if system fonts unavailable."""
    fonts = {}
    font_path = _find_system_font(language)
    for name, size in sizes.items():
        try:
            if font_path:
                fonts[name] = ImageFont.truetype(font_path, size)
            else:
                fonts[name] = ImageFont.load_default()
        except (OSError, IOError):
            fonts[name] = ImageFont.load_default()
    return fonts


def _draw_gradient(draw: ImageDraw.Draw, color_top: tuple, color_bottom: tuple):
    """Draw vertical gradient background."""
    for y in range(H):
        t = y / H
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def _center_text(draw, text, y, font, fill="white"):
    """Draw centered text at given y position."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, y), text, fill=fill, font=font)


def _wrap_text(text: str, max_chars: int = 35) -> list[str]:
    """Word-wrap text to max_chars per line."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


# --- Colors ---
BLUE_TOP = (30, 60, 180)
BLUE_BOTTOM = (70, 160, 240)
ORANGE = (255, 140, 0)
GREEN = (40, 200, 80)
RED = (220, 50, 50)
GOLD = (255, 215, 0)
DARK_TEXT = (40, 40, 80)


def render_quiz_intro(scene: dict, filename: str) -> str:
    """Render quiz intro screen with lightbulb/brain icon feel."""
    lang = scene.get("_language", "en")
    fonts = _load_fonts({"title": 64, "subtitle": 40, "icon": 120}, language=lang)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, BLUE_TOP, BLUE_BOTTOM)

    on_screen = scene.get("on_screen_text", ["Quiz Time!", "Test your knowledge"])
    title = on_screen[0] if on_screen else "Quiz Time!"
    subtitle = on_screen[1] if len(on_screen) > 1 else "Test your knowledge"

    # Lightbulb icon (circle + rays)
    cx, cy = W // 2, 700
    draw.ellipse([(cx - 80, cy - 80), (cx + 80, cy + 80)], fill=ORANGE)
    _center_text(draw, "?", cy - 55, fonts["icon"], fill="white")

    # Sparkle dots
    for dx, dy in [(-200, -40), (200, -60), (-150, 100), (180, 80), (0, -180)]:
        draw.ellipse([(cx+dx-6, cy+dy-6), (cx+dx+6, cy+dy+6)], fill=(255, 255, 255, 180))

    # Title
    _center_text(draw, title, 900, fonts["title"])

    # Subtitle
    _center_text(draw, subtitle, 1000, fonts["subtitle"], fill=(200, 220, 255))

    img.save(filename)
    return filename


def render_quiz(scene: dict, filename: str) -> str:
    """Render quiz question with 4 options."""
    lang = scene.get("_language", "en")
    fonts = _load_fonts({"question": 38, "option": 34, "badge": 36, "label": 28}, language=lang)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, BLUE_TOP, BLUE_BOTTOM)

    quiz = scene.get("quiz", {})
    question = quiz.get("question", "Question")
    options = quiz.get("options", ["A", "B", "C", "D"])

    # QUIZ badge
    badge_w, badge_h = 180, 60
    bx = (W - badge_w) // 2
    draw.rounded_rectangle([(bx, 300), (bx + badge_w, 300 + badge_h)], radius=30, fill=ORANGE)
    _center_text(draw, "QUIZ", 310, fonts["badge"])

    # Question card
    card_margin = 60
    card_top = 420
    q_lines = _wrap_text(question, 30)
    card_h = max(180, 80 + len(q_lines) * 50)
    draw.rounded_rectangle(
        [(card_margin, card_top), (W - card_margin, card_top + card_h)],
        radius=20, fill="white"
    )
    for i, line in enumerate(q_lines):
        _center_text(draw, line, card_top + 40 + i * 50, fonts["question"], fill=DARK_TEXT)

    # Options
    option_top = card_top + card_h + 60
    option_h = 80
    option_gap = 20
    labels = ["A", "B", "C", "D"]

    for i, opt in enumerate(options[:4]):
        y = option_top + i * (option_h + option_gap)
        # Option pill
        draw.rounded_rectangle(
            [(card_margin, y), (W - card_margin, y + option_h)],
            radius=40, fill="white"
        )
        # Label circle
        draw.ellipse([(card_margin + 15, y + 12), (card_margin + 55, y + 52 + 4)], fill=BLUE_TOP)
        _lx = card_margin + 25
        draw.text((_lx, y + 15), labels[i], fill="white", font=fonts["label"])
        # Option text — strip leading "A) " if present
        opt_text = opt
        if len(opt) > 3 and opt[1] == ")":
            opt_text = opt[3:].strip()
        draw.text((card_margin + 75, y + 22), opt_text, fill=DARK_TEXT, font=fonts["option"])

    img.save(filename)
    return filename


def render_quiz_answer(scene: dict, filename: str) -> str:
    """Render quiz answer reveal with correct answer highlighted."""
    lang = scene.get("_language", "en")
    fonts = _load_fonts({"title": 52, "answer": 38, "explain": 30}, language=lang)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, BLUE_TOP, BLUE_BOTTOM)

    on_screen = scene.get("on_screen_text", ["Correct!"])
    answer_text = on_screen[0] if on_screen else "Correct!"
    explanation = on_screen[1] if len(on_screen) > 1 else ""

    # Checkmark circle
    cx, cy = W // 2, 550
    draw.ellipse([(cx - 60, cy - 60), (cx + 60, cy + 60)], fill=GREEN)
    draw.text((cx - 30, cy - 35), "\u2713", fill="white", font=_load_fonts({"c": 70})["c"])

    # CORRECT title
    _center_text(draw, "CORRECT!", 660, fonts["title"], fill=GREEN)

    # Answer card
    card_margin = 60
    card_top = 760
    a_lines = _wrap_text(answer_text, 35)
    card_h = max(140, 60 + len(a_lines) * 48)
    draw.rounded_rectangle(
        [(card_margin, card_top), (W - card_margin, card_top + card_h)],
        radius=20, fill="white", outline=GREEN, width=4
    )
    for i, line in enumerate(a_lines):
        _center_text(draw, line, card_top + 30 + i * 48, fonts["answer"], fill=DARK_TEXT)

    # Explanation
    if explanation:
        exp_lines = _wrap_text(explanation, 40)
        exp_top = card_top + card_h + 40
        for i, line in enumerate(exp_lines):
            _center_text(draw, line, exp_top + i * 42, fonts["explain"], fill=(200, 220, 255))

    # Confetti dots
    import random
    rng = random.Random(42)
    for _ in range(30):
        x = rng.randint(50, W - 50)
        y = rng.randint(400, 1400)
        size = rng.randint(4, 10)
        color = rng.choice([GOLD, GREEN, ORANGE, (255, 255, 255)])
        draw.ellipse([(x, y), (x + size, y + size)], fill=color)

    img.save(filename)
    return filename


def render_score(scene: dict, filename: str) -> str:
    """Render score/celebration screen."""
    lang = scene.get("_language", "en")
    fonts = _load_fonts({"score": 72, "xp": 44, "sub": 36, "trophy": 100}, language=lang)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, BLUE_TOP, BLUE_BOTTOM)

    on_screen = scene.get("on_screen_text", ["Great Job!", "+50 XP"])
    score_text = on_screen[0] if on_screen else "Great Job!"
    xp_text = on_screen[1] if len(on_screen) > 1 else "+50 XP"

    # Trophy/star
    cx = W // 2
    draw.ellipse([(cx - 50, 500), (cx + 50, 600)], fill=GOLD)
    _center_text(draw, "\u2605", 510, fonts["xp"], fill="white")

    # Stars around
    for dx, dy in [(-180, 30), (180, 30), (-120, -60), (120, -60), (0, -100)]:
        draw.ellipse([(cx+dx-8, 550+dy-8), (cx+dx+8, 550+dy+8)], fill=GOLD)

    # Score text
    _center_text(draw, score_text, 700, fonts["score"])

    # XP badge
    badge_w = 260
    bx = (W - badge_w) // 2
    draw.rounded_rectangle([(bx, 830), (bx + badge_w, 910)], radius=40, fill=ORANGE)
    _center_text(draw, xp_text, 845, fonts["xp"])

    # Confetti
    import random
    rng = random.Random(99)
    for _ in range(40):
        x = rng.randint(50, W - 50)
        y = rng.randint(300, 1200)
        size = rng.randint(4, 12)
        color = rng.choice([GOLD, ORANGE, GREEN, (255, 255, 255), (255, 100, 100)])
        draw.ellipse([(x, y), (x + size, y + size)], fill=color)

    img.save(filename)
    return filename


def render_cta(scene: dict, filename: str) -> str:
    """Render call-to-action / streak screen."""
    lang = scene.get("_language", "en")
    fonts = _load_fonts({"streak": 48, "main": 44, "sub": 34, "button": 38, "icon": 60}, language=lang)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, BLUE_TOP, BLUE_BOTTOM)

    on_screen = scene.get("on_screen_text", ["3-Day Streak!", "Come back tomorrow"])
    streak_text = on_screen[0] if on_screen else "3-Day Streak!"
    cta_main = on_screen[1] if len(on_screen) > 1 else "Come back tomorrow!"
    cta_sub = on_screen[2] if len(on_screen) > 2 else ""

    # Flame icon
    cx = W // 2
    draw.ellipse([(cx - 45, 560), (cx + 45, 650)], fill=ORANGE)
    _center_text(draw, "\U0001f525", 555, fonts["icon"])

    # Streak text
    _center_text(draw, streak_text, 700, fonts["streak"], fill=ORANGE)

    # Main CTA
    main_lines = _wrap_text(cta_main, 30)
    for i, line in enumerate(main_lines):
        _center_text(draw, line, 800 + i * 55, fonts["main"])

    # Sub text
    if cta_sub:
        sub_lines = _wrap_text(cta_sub, 35)
        sub_top = 800 + len(main_lines) * 55 + 30
        for i, line in enumerate(sub_lines):
            _center_text(draw, line, sub_top + i * 44, fonts["sub"], fill=(200, 220, 255))

    # Button
    btn_w, btn_h = 500, 80
    bx = (W - btn_w) // 2
    btn_y = 1100
    draw.rounded_rectangle([(bx, btn_y), (bx + btn_w, btn_y + btn_h)], radius=40, fill=ORANGE)
    _center_text(draw, "Continue Tomorrow", btn_y + 18, fonts["button"])

    img.save(filename)
    return filename


def render_content_fallback(scene: dict, filename: str) -> str:
    """Fallback template for content scenes when AI image generation fails."""
    lang = scene.get("_language", "en")
    fonts = _load_fonts({"title": 48, "bullet": 38, "narration": 30}, language=lang)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    _draw_gradient(draw, BLUE_TOP, BLUE_BOTTOM)

    on_screen = scene.get("on_screen_text", [])

    # Scene number badge
    scene_num = scene.get("scene_number", "")
    badge_w, badge_h = 200, 50
    draw.rounded_rectangle([(60, 300), (60 + badge_w, 300 + badge_h)], radius=25, fill=ORANGE)
    draw.text((80, 308), f"Scene {scene_num}", fill="white", font=fonts["narration"])

    # On-screen text as bullet cards
    card_margin = 60
    y_pos = 450
    for text in on_screen:
        lines = _wrap_text(text, 32)
        card_h = max(80, 30 + len(lines) * 48)
        draw.rounded_rectangle(
            [(card_margin, y_pos), (W - card_margin, y_pos + card_h)],
            radius=16, fill=(255, 255, 255, 30)
        )
        # Accent bar
        draw.rounded_rectangle(
            [(card_margin, y_pos), (card_margin + 6, y_pos + card_h)],
            radius=3, fill=(0, 210, 210)
        )
        for i, line in enumerate(lines):
            draw.text((card_margin + 24, y_pos + 16 + i * 48), line, fill="white", font=fonts["bullet"])
        y_pos += card_h + 20

    img.save(filename)
    return filename


# Registry for easy lookup
TEMPLATE_RENDERERS = {
    "quiz_intro": render_quiz_intro,
    "quiz": render_quiz,
    "quiz_answer": render_quiz_answer,
    "score": render_score,
    "cta": render_cta,
}
