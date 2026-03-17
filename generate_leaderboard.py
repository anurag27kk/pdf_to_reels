"""
Generate a clean, pixel-perfect leaderboard image using Pillow.
No Gemini — fully programmatic for consistency.
"""

from PIL import Image, ImageDraw, ImageFont
import os

WIDTH = 1080
HEIGHT = 1920

# Colors matching the blue gradient style
BG_TOP = (30, 80, 180)       # royal blue
BG_BOTTOM = (70, 160, 230)   # sky blue
CARD_BG = (255, 255, 255)
CARD_SHADOW = (20, 60, 140, 40)
TEXT_DARK = (30, 40, 70)
TEXT_GREY = (120, 130, 160)
TEXT_WHITE = (255, 255, 255)
GOLD = (255, 195, 0)
SILVER = (180, 190, 210)
BRONZE = (205, 140, 80)
HIGHLIGHT_BG = (255, 150, 50)   # orange for "You" row
HIGHLIGHT_GLOW = (255, 180, 80, 60)
TROPHY_GOLD = (255, 200, 50)


def gradient_bg(draw, width, height, top_color, bottom_color):
    """Draw vertical gradient."""
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def rounded_rect(draw, xy, radius, fill, outline=None):
    """Draw a rounded rectangle."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline)


def draw_medal(draw, cx, cy, rank, size=36):
    """Draw a simple medal circle with rank number."""
    colors = {1: GOLD, 2: SILVER, 3: BRONZE}
    color = colors.get(rank, (200, 200, 200))

    # Outer circle
    draw.ellipse(
        [(cx - size, cy - size), (cx + size, cy + size)],
        fill=color,
    )
    # Inner darker ring
    inner = size - 6
    darker = tuple(max(0, c - 40) for c in color)
    draw.ellipse(
        [(cx - inner, cy - inner), (cx + inner, cy + inner)],
        fill=color,
        outline=darker,
        width=2,
    )


def generate_leaderboard(output_path, entries=None):
    if entries is None:
        entries = [
            {"rank": 1, "name": "Anurag", "state": "Maharashtra", "xp": 2850},
            {"rank": 2, "name": "Jai", "state": "Delhi", "xp": 2640},
            {"rank": 3, "name": "Dushyant", "state": "Karnataka", "xp": 2420},
            {"rank": 4, "name": "You", "state": "Gujarat", "xp": 2100, "is_user": True},
            {"rank": 5, "name": "Vikas", "state": "Rajasthan", "xp": 1980},
        ]

    img = Image.new("RGB", (WIDTH, HEIGHT), (30, 80, 180))
    draw = ImageDraw.Draw(img)

    # Gradient background
    gradient_bg(draw, WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)

    # Load fonts with fallback
    _font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    _fp = None
    for p in _font_paths:
        if os.path.exists(p):
            _fp = p
            break

    try:
        font_title = ImageFont.truetype(_fp, 52) if _fp else ImageFont.load_default()
        font_subtitle = ImageFont.truetype(_fp, 28) if _fp else ImageFont.load_default()
        font_name = ImageFont.truetype(_fp, 38) if _fp else ImageFont.load_default()
        font_xp = ImageFont.truetype(_fp, 42) if _fp else ImageFont.load_default()
        font_rank = ImageFont.truetype(_fp, 32) if _fp else ImageFont.load_default()
        font_label = ImageFont.truetype(_fp, 22) if _fp else ImageFont.load_default()
    except (OSError, IOError):
        font_title = ImageFont.load_default()
        font_subtitle = font_name = font_xp = font_rank = font_label = font_title

    y_start = 200

    # --- Trophy icon (simple drawn trophy) ---
    trophy_cx = WIDTH // 2
    trophy_y = y_start - 40

    # Trophy cup (trapezoid approximation using polygon)
    draw.polygon([
        (trophy_cx - 30, trophy_y - 30),
        (trophy_cx + 30, trophy_y - 30),
        (trophy_cx + 20, trophy_y + 10),
        (trophy_cx - 20, trophy_y + 10),
    ], fill=TROPHY_GOLD)
    # Trophy base
    draw.rounded_rectangle(
        [(trophy_cx - 15, trophy_y + 10), (trophy_cx + 15, trophy_y + 25)],
        radius=3, fill=TROPHY_GOLD,
    )
    draw.rounded_rectangle(
        [(trophy_cx - 25, trophy_y + 22), (trophy_cx + 25, trophy_y + 32)],
        radius=4, fill=TROPHY_GOLD,
    )

    # --- Title ---
    title = "WEEKLY LEADERBOARD"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_w = bbox[2] - bbox[0]
    draw.text(((WIDTH - title_w) // 2, y_start + 10), title, font=font_title, fill=TEXT_WHITE)

    # Subtitle
    subtitle = "Top performers this week"
    bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
    sub_w = bbox[2] - bbox[0]
    draw.text(((WIDTH - sub_w) // 2, y_start + 75), subtitle, font=font_subtitle, fill=(200, 215, 255))

    # Thin divider line
    line_y = y_start + 120
    draw.line([(80, line_y), (WIDTH - 80, line_y)], fill=(255, 255, 255, 80), width=1)

    # --- Leaderboard entries ---
    card_x = 60
    card_w = WIDTH - 120
    card_h = 110
    card_gap = 20
    card_radius = 20
    entry_start_y = line_y + 30

    for i, entry in enumerate(entries):
        y = entry_start_y + i * (card_h + card_gap)
        is_user = entry.get("is_user", False)

        # Card background
        if is_user:
            # Glow effect behind user card
            glow_pad = 6
            draw.rounded_rectangle(
                [(card_x - glow_pad, y - glow_pad),
                 (card_x + card_w + glow_pad, y + card_h + glow_pad)],
                radius=card_radius + 4,
                fill=HIGHLIGHT_GLOW,
            )
            # Orange card
            rounded_rect(draw,
                [(card_x, y), (card_x + card_w, y + card_h)],
                radius=card_radius, fill=HIGHLIGHT_BG,
            )
            name_color = TEXT_WHITE
            xp_color = TEXT_WHITE
        else:
            # White card with subtle border
            rounded_rect(draw,
                [(card_x, y), (card_x + card_w, y + card_h)],
                radius=card_radius, fill=CARD_BG,
                outline=(220, 225, 240),
            )
            name_color = TEXT_DARK
            xp_color = TEXT_DARK

        # Medal or rank number
        medal_cx = card_x + 55
        medal_cy = y + card_h // 2

        if entry["rank"] <= 3:
            draw_medal(draw, medal_cx, medal_cy, entry["rank"])
            # Rank number on medal
            rank_str = str(entry["rank"])
            bbox = draw.textbbox((0, 0), rank_str, font=font_rank)
            rw = bbox[2] - bbox[0]
            rh = bbox[3] - bbox[1]
            r_color = TEXT_WHITE if entry["rank"] == 1 else TEXT_DARK
            draw.text((medal_cx - rw // 2, medal_cy - rh // 2 - 2), rank_str, font=font_rank, fill=r_color)
        else:
            # Plain number for rank 4+
            rank_str = str(entry["rank"])
            bbox = draw.textbbox((0, 0), rank_str, font=font_rank)
            rw = bbox[2] - bbox[0]
            rh = bbox[3] - bbox[1]
            draw.text((medal_cx - rw // 2, medal_cy - rh // 2), rank_str,
                      font=font_rank, fill=TEXT_WHITE if is_user else TEXT_GREY)

        # Name (top line)
        name_x = card_x + 110
        name_y = y + 18
        draw.text((name_x, name_y), entry["name"], font=font_name, fill=name_color)

        # "YOU" badge for user row
        if is_user:
            name_w = draw.textlength(entry["name"], font=font_name)
            badge_x = name_x + name_w + 15
            badge_y = name_y + 4
            badge_w = 60
            badge_h = 32
            draw.rounded_rectangle(
                [(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
                radius=8, fill=TEXT_WHITE,
            )
            you_text = "YOU"
            bbox = draw.textbbox((0, 0), you_text, font=font_label)
            tw = bbox[2] - bbox[0]
            draw.text((badge_x + (badge_w - tw) // 2, badge_y + 5), you_text,
                      font=font_label, fill=HIGHLIGHT_BG)

        # State (bottom line, smaller)
        state = entry.get("state", "")
        if state:
            state_color = (200, 215, 255) if is_user else TEXT_GREY
            draw.text((name_x, name_y + 44), state, font=font_subtitle, fill=state_color)

        # XP
        xp_str = f"{entry['xp']:,} XP"
        xp_w = draw.textlength(xp_str, font=font_xp)
        xp_x = card_x + card_w - xp_w - 30
        xp_y = y + card_h // 2 - 24
        draw.text((xp_x, xp_y), xp_str, font=font_xp, fill=xp_color)

    # --- Bottom motivational text ---
    bottom_y = entry_start_y + len(entries) * (card_h + card_gap) + 40
    msg = "Keep learning to climb the ranks!"
    bbox = draw.textbbox((0, 0), msg, font=font_subtitle)
    msg_w = bbox[2] - bbox[0]
    draw.text(((WIDTH - msg_w) // 2, bottom_y), msg, font=font_subtitle, fill=(200, 215, 255))

    # --- "Your rank" highlight below ---
    rank_msg = "#4 in your region"
    bbox = draw.textbbox((0, 0), rank_msg, font=font_name)
    rm_w = bbox[2] - bbox[0]
    rm_y = bottom_y + 50

    # Orange pill badge
    pill_pad_x = 30
    pill_pad_y = 12
    pill_x = (WIDTH - rm_w) // 2 - pill_pad_x
    draw.rounded_rectangle(
        [(pill_x, rm_y - pill_pad_y),
         (pill_x + rm_w + pill_pad_x * 2, rm_y + 40 + pill_pad_y)],
        radius=25, fill=HIGHLIGHT_BG,
    )
    draw.text(((WIDTH - rm_w) // 2, rm_y), rank_msg, font=font_name, fill=TEXT_WHITE)

    img.save(output_path)
    print(f"Leaderboard saved: {output_path} ({os.path.getsize(output_path) / 1024:.0f} KB)")
    return output_path


if __name__ == "__main__":
    os.makedirs("output", exist_ok=True)
    generate_leaderboard("output/leaderboard_new.png")
