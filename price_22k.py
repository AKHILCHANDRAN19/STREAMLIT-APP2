import datetime
import math
import os
import shutil
import subprocess
import sys
import time
import wave
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import scrapping

# ==========================================
# CONFIGURATION & ASSET PATHS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "Fonts")
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
AUDIOS_DIR = os.path.join(BASE_DIR, "Audios")

os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(AUDIOS_DIR, exist_ok=True)

FONT_MALAYALAM = os.path.join(FONTS_DIR, "AnekMalayalam-ExtraBold.ttf")
SFX_PATH = os.path.join(AUDIOS_DIR, "price_sfx.wav")

WIDTH, HEIGHT = 1920, 1080
FPS = 30
DURATION_SEC = 7.5
DEFAULT_TOTAL_FRAMES = int(FPS * DURATION_SEC)  # 225 frames
ANIM_FRAMES = 50  # 1.6s entrance animation


# ==========================================
# UTILITIES & FONT RESOLVER
# ==========================================
def get_font(size, bold=False, malayalam=False):
    candidate_paths = [
        FONT_MALAYALAM,
        os.path.join(FONTS_DIR, "AnekMalayalam-ExtraBold.ttf"),
        os.path.join(FONTS_DIR, "Montserrat-ExtraBold.ttf" if bold else "Montserrat-Bold.ttf"),
        os.path.join(FONTS_DIR, "Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"),
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]

    for p in candidate_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_text_safe(
    draw_img,
    text,
    pos,
    size,
    color,
    bold=False,
    align="center",
    multiline=False,
    line_spacing=6,
    malayalam=False,
):
    font = get_font(size, bold=bold, malayalam=malayalam)
    draw = ImageDraw.Draw(draw_img)
    if multiline:
        draw.multiline_text(
            pos,
            text,
            fill=color,
            font=font,
            align=align,
            anchor="ma",
            spacing=line_spacing,
        )
    else:
        anchor = "mm" if align == "center" else ("lm" if align == "left" else "rm")
        draw.text(pos, text, fill=color, font=font, anchor=anchor)


def ease_out_back(t, overshoot=1.4):
    t = min(1.0, max(0.0, t))
    t -= 1.0
    return t * t * ((overshoot + 1.0) * t + overshoot) + 1.0


def linear_gradient_2d(width, height, color_top, color_bot):
    if width <= 0 or height <= 0:
        return np.zeros((max(1, height), max(1, width), 4), dtype=np.uint8)
    y = np.linspace(0, 1, height)[:, None]
    c_top = np.array(color_top, dtype=np.float32)
    c_bot = np.array(color_bot, dtype=np.float32)
    grad = (1.0 - y) * c_top + y * c_bot
    return np.tile(grad[:, None, :], (1, width, 1)).astype(np.uint8)


# ==========================================
# PROCEDURAL SOUND SYNTHESIZER (WAVE)
# ==========================================
def synthesize_price_sfx(output_path, total_duration, sample_rate=44100):
    """
    Synthesizes custom cinematic audio:
    1. Pillar rise whoosh & thud (0.0s - 0.7s)
    2. Card spring-drop swoosh and lock (0.4s - 1.1s)
    3. Rapid digital cash register counter ticks (0.6s - 1.5s)
    4. Warm low ambient pad underlying the audio
    """
    total_samples = int(total_duration * sample_rate)
    left = np.zeros(total_samples, dtype=np.float32)
    right = np.zeros(total_samples, dtype=np.float32)

    def inject(start_sec, s_l, s_r):
        st = int(start_sec * sample_rate)
        ed = min(total_samples, st + len(s_l))
        vl = ed - st
        if vl > 0:
            left[st:ed] += s_l[:vl]
            right[st:ed] += s_r[:vl]

    # 1. Pillar Riser & Solid Thud (t = 0.1s)
    t1 = np.linspace(0, 0.9, int(sample_rate * 0.9), endpoint=False)
    sub = np.sin(2.0 * np.pi * (110.0 * np.exp(-t1 * 3.5) + 38.0) * t1) * np.exp(-t1 * 2.8) * 0.55
    punch = np.random.uniform(-1.0, 1.0, len(t1)) * np.exp(-t1 * 35.0) * 0.25
    thud = sub + punch
    inject(0.1, thud, thud)

    # 2. Card Spring-Drop Swoosh (t = 0.45s)
    t2 = np.linspace(0, 0.8, int(sample_rate * 0.8), endpoint=False)
    swoosh_freq = 450.0 * np.exp(-t2 * 4.0) + 120.0
    swoosh = np.sin(2.0 * np.pi * np.cumsum(swoosh_freq) / sample_rate) * np.exp(-t2 * 4.0) * 0.35
    lock = np.sin(2.0 * np.pi * 840.0 * t2) * np.exp(-t2 * 25.0) * 0.25
    card_sfx = swoosh + lock
    inject(0.45, card_sfx * 0.85, card_sfx * 0.95)

    # 3. Rapid Digital Counter Ticks (t = 0.6s - 1.5s)
    tick_dur = 0.03
    t_tick = np.linspace(0, tick_dur, int(sample_rate * tick_dur), endpoint=False)
    single_tick = (np.sin(2.0 * np.pi * 2400.0 * t_tick) + 0.4 * np.sin(2.0 * np.pi * 3600.0 * t_tick)) * np.exp(-t_tick * 120.0) * 0.22

    for k in range(16):
        tick_time = 0.60 + k * 0.05
        inject(tick_time, single_tick * 0.9, single_tick * 1.1)

    # 4. Low warm ambient tone
    t_amb = np.linspace(0, total_duration, total_samples, endpoint=False)
    amb = np.sin(2.0 * np.pi * 120.0 * t_amb) * 0.04
    left += amb
    right += amb

    # Soft limiter & 16-bit PCM conversion
    left = (np.tanh(left) * 32767).astype(np.int16)
    right = (np.tanh(right) * 32767).astype(np.int16)

    interleaved = np.empty((left.size + right.size,), dtype=np.int16)
    interleaved[0::2] = left
    interleaved[1::2] = right

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(interleaved.tobytes())


# ==========================================
# 3D PILLAR & GROWING DOTTED LINE RENDERER
# ==========================================
def draw_animated_pillar(canvas, cx, cy_base, rx, ry, height, theme, local_progress):
    if height <= 4:
        return

    W, H = canvas.size
    top_y = cy_base - height

    b_bot = (cx, cy_base + ry)
    b_lft = (cx - rx, cy_base)
    b_rgt = (cx + rx, cy_base)

    t_top = (cx, top_y - ry)
    t_bot = (cx, top_y + ry)
    t_lft = (cx - rx, top_y)
    t_rgt = (cx + rx, top_y)

    # 1. Left Face (Vibrant Gradient Wall)
    left_poly = np.array([t_lft, t_bot, b_bot, b_lft], dtype=np.int32)
    lx, ly, lw, lh = cv2.boundingRect(left_poly)
    if lw > 0 and lh > 0:
        mask_l = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask_l, [left_poly], 255)
        grad_l = linear_gradient_2d(lw, lh, theme["left_top"], theme["left_bot"])
        face_l = np.zeros((H, W, 4), dtype=np.uint8)
        crop_m_l = mask_l[ly : ly + lh, lx : lx + lw]
        face_l[ly : ly + lh, lx : lx + lw][crop_m_l > 0] = grad_l[crop_m_l > 0]
    else:
        face_l = np.zeros((H, W, 4), dtype=np.uint8)

    # 2. Right Face (Volume Depth)
    right_poly = np.array([t_bot, t_rgt, b_rgt, b_bot], dtype=np.int32)
    rx_b, ry_b, rw, rh = cv2.boundingRect(right_poly)
    if rw > 0 and rh > 0:
        mask_r = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask_r, [right_poly], 255)
        grad_r = linear_gradient_2d(rw, rh, theme["right_top"], theme["right_bot"])
        face_r = np.zeros((H, W, 4), dtype=np.uint8)
        crop_m_r = mask_r[ry_b : ry_b + rh, rx_b : rx_b + rw]
        face_r[ry_b : ry_b + rh, rx_b : rx_b + rw][crop_m_r > 0] = grad_r[crop_m_r > 0]
    else:
        face_r = np.zeros((H, W, 4), dtype=np.uint8)

    canvas.alpha_composite(Image.fromarray(cv2.add(face_l, face_r)))

    # 3. Top Diamond Face
    top_poly = np.array([t_top, t_rgt, t_bot, t_lft], dtype=np.int32)
    tx, ty, tw, th = cv2.boundingRect(top_poly)
    if tw > 0 and th > 0:
        mask_t = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask_t, [top_poly], 255)
        grad_t = linear_gradient_2d(tw, th, theme["top_light"], theme["top_dark"])
        face_t = np.zeros((H, W, 4), dtype=np.uint8)
        crop_m_t = mask_t[ty : ty + th, tx : tx + tw]
        face_t[ty : ty + th, tx : tx + tw][crop_m_t > 0] = grad_t[crop_m_t > 0]
        canvas.alpha_composite(Image.fromarray(face_t))

    # 4. Specular Edges
    edge_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    e_draw = ImageDraw.Draw(edge_layer)
    e_draw.line([t_lft, t_top, t_rgt], fill=(255, 255, 255, 230), width=2)
    e_draw.line([t_lft, t_bot, t_rgt], fill=(255, 255, 255, 170), width=2)
    e_draw.line([t_bot, b_bot], fill=(255, 255, 255, 90), width=2)
    e_draw.line([b_lft, b_bot, b_rgt], fill=(255, 255, 255, 120), width=1)
    canvas.alpha_composite(edge_layer)

    # 5. Dotted Line & Floating Numbers
    if local_progress > 0.05:
        line_growth = min(1.0, local_progress / 0.85)
        dash_len = int(75 * line_growth)
        alpha = int(255 * min(1.0, local_progress / 0.35))

        anno_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a_draw = ImageDraw.Draw(anno_layer)

        dash_start_y = t_top[1] - 8
        dash_end_y = dash_start_y - dash_len
        curr_y = dash_start_y
        while curr_y > dash_end_y:
            a_draw.line(
                [(cx, curr_y), (cx, max(dash_end_y, curr_y - 6))],
                fill=(130, 150, 170, int(200 * (alpha / 255.0))),
                width=2,
            )
            curr_y -= 12
        canvas.alpha_composite(anno_layer)

        num_color = (*theme["icon_color"][:3], alpha)
        draw_text_safe(
            canvas,
            theme["top_num"],
            (cx, dash_end_y - 18),
            size=36,
            color=num_color,
            bold=True,
            align="center",
        )


# ==========================================
# PRE-RENDER GOLD PRICE CARD BASE
# ==========================================
def pre_render_gold_card_base(box_w, box_h):
    padding = 45
    total_w = box_w + padding * 2
    total_h = box_h + padding * 2
    card = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    bx, by = padding, padding
    draw = ImageDraw.Draw(card)

    # Card Base Container
    draw.rounded_rectangle(
        [(bx, by), (bx + box_w - 1, by + box_h - 1)],
        radius=36,
        fill=(255, 255, 255, 252),
        outline=(255, 205, 80, 230),
        width=3,
    )

    # Header Banner: "ഇന്നത്തെ സ്വർണ്ണവില"
    header_w = box_w - 60
    header_h = 76
    hx, hy = bx + 30, by + 30
    draw.rounded_rectangle(
        [(hx, hy), (hx + header_w, hy + header_h)],
        radius=20,
        fill=(255, 160, 0, 255),
        outline=(255, 220, 90, 255),
        width=2,
    )
    draw_text_safe(
        card,
        "ഇന്നത്തെ സ്വർണ്ണവില",
        (hx + header_w // 2, hy + header_h // 2 + 1),
        size=38,
        color=(255, 255, 255, 255),
        bold=True,
        align="center",
        malayalam=True,
    )

    # Badge Pill: "22K • 916 BIS HALLMARKED"
    badge_y = hy + header_h + 20
    badge_w, badge_h = 280, 36
    p_x = bx + (box_w - badge_w) // 2
    draw.rounded_rectangle(
        [(p_x, badge_y), (p_x + badge_w, badge_y + badge_h)],
        radius=14,
        fill=(245, 248, 252, 255),
        outline=(220, 230, 242, 255),
        width=1,
    )
    draw_text_safe(
        card,
        "22K  •  916 BIS HALLMARKED",
        (p_x + badge_w // 2, badge_y + badge_h // 2),
        size=18,
        color=(110, 130, 155, 255),
        bold=True,
        align="center",
    )

    # Row 1 Shell (1 Gram) - Expanded Height for Large Font
    row1_y = badge_y + 64
    row_h = 100
    draw.rounded_rectangle(
        [(bx + 30, row1_y), (bx + box_w - 30, row1_y + row_h)],
        radius=20,
        fill=(248, 252, 255, 255),
        outline=(220, 238, 250, 255),
        width=2,
    )
    draw_text_safe(
        card,
        "1 ഗ്രാം",
        (bx + 60, row1_y + row_h // 2),
        size=42,
        color=(45, 65, 90, 255),
        bold=True,
        align="left",
        malayalam=True,
    )

    # Row 2 Shell (1 Pavan) - Expanded Height for Large Font
    row2_y = row1_y + row_h + 22
    draw.rounded_rectangle(
        [(bx + 30, row2_y), (bx + box_w - 30, row2_y + row_h)],
        radius=20,
        fill=(255, 248, 250, 255),
        outline=(255, 220, 230, 255),
        width=2,
    )
    draw_text_safe(
        card,
        "1 പവൻ",
        (bx + 60, row2_y + row_h // 2),
        size=42,
        color=(45, 65, 90, 255),
        bold=True,
        align="left",
        malayalam=True,
    )

    # Footer Text
    footer_y = by + box_h - 38
    draw_text_safe(
        card,
        "LIVE MARKET UPDATE",
        (bx + box_w // 2 + 15, footer_y),
        size=17,
        color=(125, 145, 170, 255),
        bold=True,
        align="center",
    )

    return card, padding, row1_y, row2_y, row_h, footer_y


# ==========================================
# MAIN PIPELINE
# ==========================================
def main(source="goodreturns", duration_sec=None, output_override=None):
    start_time = time.time()

    print(f"\n[DATA] Fetching live rates from {source}...")
    gr_data = scrapping.scrape_goodreturns_22k()
    
    if source == "akgsma":
        akg_data = scrapping.scrape_akgsma_22k()
        today_1g = akg_data.get('today_1g', gr_data.get('today_1g', 0))
    else:
        today_1g = gr_data.get('today_1g', 0)
        
    yest_1g = gr_data.get('yest_1g', 0)
    today_8g = today_1g * 8

    # Dynamic duration handling
    effective_duration = float(duration_sec) if duration_sec and duration_sec > 1.0 else DURATION_SEC
    TOTAL_FRAMES = int(FPS * effective_duration)

    # Synthesize synchronized procedural audio
    synthesize_price_sfx(SFX_PATH, total_duration=effective_duration)

    # Dynamic Height adjustment matching relative trends
    if today_1g >= yest_1g:
        yest_h = 470
        today_h = 620
    else:
        yest_h = 620
        today_h = 470

    # Pre-render Background
    bg_np = linear_gradient_2d(WIDTH, HEIGHT, (244, 248, 252, 255), (232, 240, 248, 255))
    base_bg = Image.fromarray(bg_np)

    today_dt = datetime.datetime.now()
    yesterday_dt = today_dt - datetime.timedelta(days=1)

    def format_date_text(d):
        m_str = d.strftime("%b")
        if m_str.lower() == "sep":
            m_str = "Sept"
        return f"{d.strftime('%d')}\n{m_str}\n{d.strftime('%Y')}"

    date_yesterday = format_date_text(yesterday_dt)
    date_today = format_date_text(today_dt)

    rx, ry, cy_base = 92, 46, 920

    THEME_TURQUOISE = {
        "icon_color": (0, 170, 155, 255),
        "top_light": (0, 255, 210, 255),
        "top_dark": (0, 185, 165, 255),
        "left_top": (0, 200, 185, 245),
        "left_bot": (175, 255, 230, 165),
        "right_top": (0, 145, 135, 255),
        "right_bot": (130, 245, 210, 185),
    }

    THEME_RED = {
        "icon_color": (230, 25, 90, 255),
        "top_light": (255, 75, 125, 255),
        "top_dark": (200, 10, 80, 255),
        "left_top": (205, 15, 85, 245),
        "left_bot": (255, 130, 165, 175),
        "right_top": (160, 5, 65, 255),
        "right_bot": (255, 95, 140, 195),
    }

    if today_1g >= yest_1g:
        yest_theme = THEME_RED
        today_theme = THEME_TURQUOISE
    else:
        yest_theme = THEME_TURQUOISE
        today_theme = THEME_RED

    columns = [
        {"cx": 360, "target_h": yest_h, "top_num": f"₹{int(yest_1g)}", "date_text": date_yesterday, "stagger_start": 0, **yest_theme},
        {"cx": 780, "target_h": today_h, "top_num": f"₹{int(today_1g)}", "date_text": date_today, "stagger_start": 10, **today_theme},
    ]

    for col in columns:
        draw_text_safe(
            base_bg,
            col["date_text"],
            (col["cx"] - rx - 85, cy_base - 140),
            size=26,
            color=(90, 110, 135, 255),
            bold=True,
            align="center",
            multiline=True,
            line_spacing=6,
        )

    # Pre-render Gold Card Base Shell
    box_w, box_h = 760, 550
    target_box_x, target_box_y = 1060, 260
    card_base, pad, r1_y, r2_y, row_h, footer_y = pre_render_gold_card_base(box_w, box_h)

    # 1-PIXEL MICRO-GOLD DUST PARTICLES (1,400 particles)
    np.random.seed(42)
    P_COUNT = 1400
    p_x = np.random.uniform(0, WIDTH, P_COUNT).astype(np.float32)
    p_y = np.random.uniform(0, HEIGHT, P_COUNT).astype(np.float32)
    p_vx = np.random.uniform(-0.5, 0.5, P_COUNT).astype(np.float32)
    p_vy = np.random.uniform(-1.2, -0.3, P_COUNT).astype(np.float32)  # Gentle upward float
    p_sparkle = np.random.uniform(0, 2 * math.pi, P_COUNT).astype(np.float32)

    gold_colors_bgr = np.array([
        [40, 215, 255],   # Radiant Gold
        [20, 185, 255],   # Classic Pure Gold
        [10, 145, 235],   # Warm Deep Gold
        [190, 240, 255],  # Specular Light Gold
    ], dtype=np.uint8)
    p_color_idx = np.random.randint(0, len(gold_colors_bgr), P_COUNT)

    output_video_path = output_override or os.path.join(VIDEOS_DIR, "price_22k.mp4")

    # Encode with FFmpeg muxing procedural audio
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "bgr24", "-r", str(FPS), "-i", "-",
        "-i", SFX_PATH,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-pix_fmt", "yuv420p", "-t", str(effective_duration),
        "-movflags", "+faststart", output_video_path,
    ]

    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    print(f"\n🚀 Rendering High-Impact 22K Graphics (Total {TOTAL_FRAMES} frames @ {FPS} FPS)...")

    # ==================================================
    # MASTER RENDER LOOP
    # ==================================================
    for frame_idx in range(TOTAL_FRAMES):
        frame = base_bg.copy()
        t_sec = frame_idx / FPS

        # 1. Update 1px Micro-Gold Dust Particles
        p_x += p_vx
        p_y += p_vy
        p_x %= WIDTH
        p_y %= HEIGHT

        # 2. Render Left 3D Pillars (Entrance + Breathing micro-pulse)
        for col in columns:
            local_frame = frame_idx - col["stagger_start"]
            if local_frame < 0:
                continue

            dur = 24.0
            if local_frame <= dur:
                t_bar = min(1.0, local_frame / dur)
                bar_ease = ease_out_back(t_bar, overshoot=1.35)
                current_h = int(col["target_h"] * bar_ease)
            else:
                t_bar = 1.0
                # Organic breathing micro-pulse once arrived
                pulse = math.sin(frame_idx * 0.09 + col["stagger_start"]) * 2.5
                current_h = int(col["target_h"] + pulse)

            draw_animated_pillar(
                frame,
                col["cx"],
                cy_base,
                rx,
                ry,
                current_h,
                col,
                t_bar,
            )

        # 3. Gold Card Drop & Elastic Bounce
        t_box = min(1.0, frame_idx / 35.0)
        box_ease = ease_out_back(t_box, overshoot=1.45)
        current_box_y = int(-box_h + (target_box_y + box_h) * box_ease)

        if current_box_y + box_h > 0:
            # Dynamic Card Layer
            card_dynamic = card_base.copy()
            c_draw = ImageDraw.Draw(card_dynamic)
            bx_c = pad

            # Digital Price Counter Roll-up (Interpolating during entrance)
            if frame_idx < 15:
                count_ratio = 0.0
            elif frame_idx < 45:
                t_c = (frame_idx - 15) / 30.0
                count_ratio = 1.0 - (1.0 - t_c) ** 3
            else:
                count_ratio = 1.0

            curr_1g_val = int(today_1g * count_ratio)
            curr_8g_val = int(today_8g * count_ratio)

            price_1g_txt = f"₹ {curr_1g_val:,} /-"
            price_8g_txt = f"₹ {curr_8g_val:,} /-"

            # MAXIMIZED 60px ExtraBold Price Numerals
            draw_text_safe(
                card_dynamic,
                price_1g_txt,
                (bx_c + box_w - 55, r1_y + row_h // 2),
                size=60,
                color=(0, 165, 145, 255),
                bold=True,
                align="right",
            )
            draw_text_safe(
                card_dynamic,
                price_8g_txt,
                (bx_c + box_w - 55, r2_y + row_h // 2),
                size=60,
                color=(235, 25, 95, 255),
                bold=True,
                align="right",
            )

            # Live Radar Dot Animation
            dot_cx = bx_c + box_w // 2 - 100
            dot_cy = footer_y
            c_draw.ellipse([(dot_cx - 6, dot_cy - 6), (dot_cx + 6, dot_cy + 6)], fill=(34, 197, 94, 255))

            # Radar expanding ping ring (repeats every 2 seconds)
            ping_prog = (frame_idx % 60) / 60.0
            ping_rad = int(6 + ping_prog * 18)
            ping_alpha = int(220 * (1.0 - ping_prog))
            c_draw.ellipse(
                [(dot_cx - ping_rad, dot_cy - ping_rad), (dot_cx + ping_rad, dot_cy + ping_rad)],
                outline=(34, 197, 94, ping_alpha),
                width=2,
            )

            # Pulsing Neon Glow Layer Behind Card
            glow_pulse = 0.85 + 0.15 * math.sin(frame_idx * 0.12)
            glow_alpha = int(55 * glow_pulse)
            glow_img = Image.new("RGBA", card_dynamic.size, (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(glow_img)
            g_draw.rounded_rectangle(
                [(pad - 12, pad - 12), (pad + box_w + 12, pad + box_h + 12)],
                radius=42,
                fill=(255, 195, 45, glow_alpha),
            )
            glow_blurred = cv2.GaussianBlur(np.array(glow_img), (35, 35), sigmaX=14, sigmaY=14)
            card_with_glow = Image.fromarray(glow_blurred)
            card_with_glow.alpha_composite(card_dynamic)

            frame.alpha_composite(card_with_glow, (target_box_x - pad, current_box_y - pad))

        # Convert to BGR array for 1px Particle Rendering
        frame_bgr = cv2.cvtColor(np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR)

        # 4. Draw 1-Pixel Micro-Gold Dust & Diamond Sparkles
        xi = p_x.astype(np.int32)
        yi = p_y.astype(np.int32)
        valid = (xi >= 0) & (xi < WIDTH) & (yi >= 0) & (yi < HEIGHT)
        valid_idx = np.where(valid)[0]

        # Twinkle calculation
        twinkle = np.sin(frame_idx * 0.18 + p_sparkle[valid_idx])
        is_sparkle = twinkle > 0.82

        # Assign standard 1px gold colors
        frame_bgr[yi[valid_idx], xi[valid_idx]] = gold_colors_bgr[p_color_idx[valid_idx]]
        # Assign bright specular white-gold diamond sparkles
        if np.any(is_sparkle):
            sp_idx = valid_idx[is_sparkle]
            frame_bgr[yi[sp_idx], xi[sp_idx]] = [255, 255, 255]

        ffmpeg_proc.stdin.write(frame_bgr.tobytes())

    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()

    elapsed = time.time() - start_time
    print(f"\n✅ Done in {elapsed:.2f}s | Path:\n{output_video_path}\n")
    return output_video_path


if __name__ == "__main__":
    main()
