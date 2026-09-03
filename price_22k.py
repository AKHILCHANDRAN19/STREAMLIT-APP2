import datetime
import math
import os
import shutil
import subprocess
import sys
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import scrapping

# ==========================================
# CONFIGURATION & ASSET PATHS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "Fonts")
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

FONT_MALAYALAM = os.path.join(FONTS_DIR, "AnekMalayalam-ExtraBold.ttf")

WIDTH, HEIGHT = 1920, 1080
FPS = 30
DURATION_SEC = 7.0
DEFAULT_TOTAL_FRAMES = int(FPS * DURATION_SEC)  # 210 frames
ANIM_FRAMES = 50  # 1.6s dynamic animation


# ==========================================
# UTILITIES & FONT RESOLVER
# ==========================================
def get_font(size, bold=False, malayalam=False):
    candidate_paths = [
        FONT_MALAYALAM,
        os.path.join(FONTS_DIR, "AnekMalayalam-ExtraBold.ttf"),
        os.path.join(FONTS_DIR, "Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"),
        os.path.join(FONTS_DIR, "Montserrat-ExtraBold.ttf" if bold else "Montserrat-Bold.ttf"),
        "AnekMalayalam-ExtraBold.ttf",
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
        "/system/fonts/NotoSans-Bold.ttf" if bold else "/system/fonts/NotoSans-Regular.ttf",
        "/system/fonts/DroidSans-Bold.ttf" if bold else "/system/fonts/DroidSans.ttf",
        "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]

    for p in candidate_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return None


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
    if font is not None:
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
            anchor = (
                "mm"
                if align == "center"
                else ("lm" if align == "left" else "rm")
            )
            draw.text(pos, text, fill=color, font=font, anchor=anchor)
    else:
        # Fallback Vector Text
        img_np = np.array(draw_img)
        font_face = cv2.FONT_HERSHEY_DUPLEX if bold else cv2.FONT_HERSHEY_SIMPLEX
        scale = size / 30.0
        thickness = 2 if bold else 1

        if multiline:
            lines = text.split("\n")
            curr_y = int(pos[1])
            for line in lines:
                (tw, th), _ = cv2.getTextSize(
                    line, font_face, scale, thickness
                )
                tx = int(pos[0] - tw / 2) if align == "center" else int(pos[0])
                cv2.putText(
                    img_np,
                    line,
                    (tx, curr_y + th),
                    font_face,
                    scale,
                    color[:3],
                    thickness,
                    cv2.LINE_AA,
                )
                curr_y += th + line_spacing + 6
        else:
            (tw, th), _ = cv2.getTextSize(text, font_face, scale, thickness)
            tx = int(pos[0] - tw / 2) if align == "center" else int(pos[0])
            ty = int(pos[1] + th / 2)
            cv2.putText(
                img_np,
                text,
                (tx, ty),
                font_face,
                scale,
                color[:3],
                thickness,
                cv2.LINE_AA,
            )
        draw_img.paste(Image.fromarray(img_np))


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
# 3D PILLAR & GROWING DOTTED LINE RENDERER
# ==========================================
def draw_animated_pillar(
    canvas, cx, cy_base, rx, ry, height, theme, local_progress
):
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
        grad_l = linear_gradient_2d(
            lw, lh, theme["left_top"], theme["left_bot"]
        )
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
        grad_r = linear_gradient_2d(
            rw, rh, theme["right_top"], theme["right_bot"]
        )
        face_r = np.zeros((H, W, 4), dtype=np.uint8)
        crop_m_r = mask_r[ry_b : ry_b + rh, rx_b : rx_b + rw]
        face_r[ry_b : ry_b + rh, rx_b : rx_b + rw][crop_m_r > 0] = grad_r[
            crop_m_r > 0
        ]
    else:
        face_r = np.zeros((H, W, 4), dtype=np.uint8)

    canvas.alpha_composite(Image.fromarray(cv2.add(face_l, face_r)))

    # 3. Top Diamond Face
    top_poly = np.array([t_top, t_rgt, t_bot, t_lft], dtype=np.int32)
    tx, ty, tw, th = cv2.boundingRect(top_poly)
    if tw > 0 and th > 0:
        mask_t = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask_t, [top_poly], 255)
        grad_t = linear_gradient_2d(
            tw, th, theme["top_light"], theme["top_dark"]
        )
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

    # 5. Dotted Line & Floating Numbers Growing with Animation
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

        # Number rides dynamically on the tip of the rising dotted line
        num_color = (*theme["icon_color"][:3], alpha)
        draw_text_safe(
            canvas,
            theme["top_num"],
            (cx, dash_end_y - 18),
            size=34,
            color=num_color,
            bold=True,
            align="center",
        )


# ==========================================
# PRE-RENDER MALAYALAM GOLD PRICE BOX
# ==========================================
def pre_render_gold_card_with_glow(box_w, box_h, price_1g_str, price_8g_str):
    padding = 40
    total_w = box_w + padding * 2
    total_h = box_h + padding * 2
    full_card = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))

    # Glow Layer
    glow = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.rounded_rectangle(
        [(padding - 10, padding - 10), (padding + box_w + 10, padding + box_h + 10)],
        radius=40,
        fill=(255, 195, 45, 55),
    )
    glow_blurred = cv2.GaussianBlur(np.array(glow), (31, 31), sigmaX=12, sigmaY=12)
    full_card.alpha_composite(Image.fromarray(glow_blurred))

    # Card Base
    card_draw = ImageDraw.Draw(full_card)
    bx, by = padding, padding

    card_draw.rounded_rectangle(
        [(bx, by), (bx + box_w - 1, by + box_h - 1)],
        radius=32,
        fill=(255, 255, 255, 250),
        outline=(255, 205, 80, 220),
        width=3,
    )

    # Header Banner
    header_w = box_w - 60
    header_h = 76
    hx, hy = bx + 30, by + 30
    card_draw.rounded_rectangle(
        [(hx, hy), (hx + header_w, hy + header_h)],
        radius=20,
        fill=(255, 160, 0, 255),
        outline=(255, 220, 90, 255),
        width=2,
    )

    # Title: "ഇന്നത്തെ സ്വർണ്ണവില"
    draw_text_safe(
        full_card,
        "ഇന്നത്തെ സ്വർണ്ണവില",
        (hx + header_w // 2, hy + header_h // 2 + 1),
        size=36,
        color=(255, 255, 255, 255),
        bold=True,
        align="center",
        malayalam=True,
    )

    # Badge Pill
    badge_y = hy + header_h + 24
    badge_w, badge_h = 260, 34
    p_x = bx + (box_w - badge_w) // 2
    card_draw.rounded_rectangle(
        [(p_x, badge_y), (p_x + badge_w, badge_y + badge_h)],
        radius=12,
        fill=(245, 248, 252, 255),
        outline=(220, 230, 242, 255),
        width=1,
    )
    draw_text_safe(
        full_card,
        "22K  •  916 BIS HALLMARKED",
        (p_x + badge_w // 2, badge_y + badge_h // 2),
        size=17,
        color=(110, 130, 155, 255),
        bold=True,
        align="center",
    )

    # Row 1 (1 Gram)
    row1_y = badge_y + 80
    card_draw.rounded_rectangle(
        [(bx + 35, row1_y - 20), (bx + box_w - 35, row1_y + 55)],
        radius=16,
        fill=(248, 251, 255, 255),
        outline=(225, 238, 248, 255),
        width=1,
    )
    draw_text_safe(
        full_card,
        "1 ഗ്രാം",
        (bx + 65, row1_y + 16),
        size=32,
        color=(45, 65, 90, 255),
        bold=True,
        align="left",
        malayalam=True,
    )
    draw_text_safe(
        full_card,
        price_1g_str,
        (bx + box_w - 65, row1_y + 16),
        size=36,
        color=(0, 160, 145, 255),
        bold=True,
        align="right",
        malayalam=True,
    )

    # Row 2 (1 Pavan)
    row2_y = row1_y + 105
    card_draw.rounded_rectangle(
        [(bx + 35, row2_y - 20), (bx + box_w - 35, row2_y + 55)],
        radius=16,
        fill=(255, 248, 250, 255),
        outline=(255, 220, 230, 255),
        width=1,
    )
    draw_text_safe(
        full_card,
        "1 പവൻ",
        (bx + 65, row2_y + 16),
        size=32,
        color=(45, 65, 90, 255),
        bold=True,
        align="left",
        malayalam=True,
    )
    draw_text_safe(
        full_card,
        price_8g_str,
        (bx + box_w - 65, row2_y + 16),
        size=36,
        color=(235, 25, 95, 255),
        bold=True,
        align="right",
        malayalam=True,
    )

    # Footer
    footer_y = by + box_h - 40
    card_draw.ellipse(
        [(bx + box_w // 2 - 105, footer_y - 6), (bx + box_w // 2 - 93, footer_y + 6)],
        fill=(34, 197, 94, 255),
    )
    draw_text_safe(
        full_card,
        "LIVE MARKET UPDATE",
        (bx + box_w // 2 + 10, footer_y),
        size=16,
        color=(125, 145, 170, 255),
        bold=True,
        align="center",
    )

    return full_card, padding


# ==========================================
# MAIN PIPELINE
# ==========================================
def main(source="goodreturns", duration_sec=None, output_override=None):
    start_time = time.time()

    print(f"\n[DATA] Fetching live data from {source}...")
    gr_data = scrapping.scrape_goodreturns_22k()
    
    if source == "akgsma":
        akg_data = scrapping.scrape_akgsma_22k()
        today_1g = akg_data.get('today_1g', gr_data.get('today_1g', 0))
    else:
        today_1g = gr_data.get('today_1g', 0)
        
    yest_1g = gr_data.get('yest_1g', 0)
    today_8g = today_1g * 8

    # Dynamic Frame Count driven by Audio Duration
    if duration_sec:
        TOTAL_FRAMES = max(DEFAULT_TOTAL_FRAMES, int(FPS * duration_sec))
    else:
        TOTAL_FRAMES = DEFAULT_TOTAL_FRAMES

    # Dynamic Height adjustment matching relative trends
    if today_1g >= yest_1g:
        yest_h = 470
        today_h = 620
    else:
        yest_h = 620
        today_h = 470

    # Pre-render Background Layer
    bg_np = linear_gradient_2d(
        WIDTH, HEIGHT, (244, 248, 252, 255), (232, 240, 248, 255)
    )
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

    # =========================================================================
    # THE TWO EXACT COLOR PALETTES FROM YOUR SCRIPT
    # =========================================================================
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

    # Dynamic opposing contrast
    if today_1g >= yest_1g:
        yest_theme = THEME_RED
        today_theme = THEME_TURQUOISE
    else:
        yest_theme = THEME_TURQUOISE
        today_theme = THEME_RED

    columns = [
        # Bar 1: Yesterday's Bar
        {
            "cx": 360,
            "target_h": yest_h,
            "top_num": f"₹{int(yest_1g)}",
            "date_text": date_yesterday,
            "stagger_start": 0,
            **yest_theme
        },
        # Bar 2: Today's Bar
        {
            "cx": 780,
            "target_h": today_h,
            "top_num": f"₹{int(today_1g)}",
            "date_text": date_today,
            "stagger_start": 10,
            **today_theme
        },
    ]

    # Pre-render dynamic dates on the left of each bar
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

    # Pre-render Right Gold Card
    box_w, box_h = 740, 520
    target_box_x, target_box_y = 1080, 280
    price_1g_str = f"₹ {int(today_1g):,} /-"
    price_8g_str = f"₹ {int(today_8g):,} /-"

    cached_box_with_glow, pad = pre_render_gold_card_with_glow(
        box_w, box_h, price_1g_str, price_8g_str
    )

    output_video_path = output_override or os.path.join(VIDEOS_DIR, "price_22k.mp4")

    # Encode with FFmpeg pipe (or cv2 fallback)
    has_ffmpeg = shutil.which("ffmpeg") is not None
    ffmpeg_proc = None
    cv_writer = None

    if has_ffmpeg:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{WIDTH}x{HEIGHT}",
            "-pix_fmt",
            "bgr24",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_video_path,
        ]
        ffmpeg_proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    else:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        cv_writer = cv2.VideoWriter(
            output_video_path, fourcc, FPS, (WIDTH, HEIGHT)
        )

    def write_frame_bytes(bgr_bytes):
        if ffmpeg_proc:
            ffmpeg_proc.stdin.write(bgr_bytes)
        else:
            cv_writer.write(
                np.frombuffer(bgr_bytes, dtype=np.uint8).reshape(
                    (HEIGHT, WIDTH, 3)
                )
            )

    print(f"\n🚀 Rendering Sequential Animation (Total {TOTAL_FRAMES} frames @ {FPS} FPS)...")

    # Phase 1: Sequential Ripple Motion
    for frame_idx in range(ANIM_FRAMES):
        frame = base_bg.copy()

        # Render Left Pillars with Sequential Stagger
        for col in columns:
            local_frame = frame_idx - col["stagger_start"]
            if local_frame < 0:
                continue

            dur = 24.0
            t_bar = min(1.0, local_frame / dur)
            bar_ease = ease_out_back(t_bar, overshoot=1.35)
            current_h = int(col["target_h"] * bar_ease)

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

        # Right Gold Card Drops simultaneously with Elastic Bounce
        t_box = min(1.0, frame_idx / 35.0)
        box_ease = ease_out_back(t_box, overshoot=1.45)
        current_box_y = int(-box_h + (target_box_y + box_h) * box_ease)

        if current_box_y + box_h > 0:
            frame.alpha_composite(
                cached_box_with_glow,
                (target_box_x - pad, current_box_y - pad),
            )

        frame_bgr = cv2.cvtColor(
            np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR
        )
        write_frame_bytes(frame_bgr.tobytes())

    # Phase 2: Fully Extended Hold Frames (Covers full audio length without freezing or cutting)
    final_frame = base_bg.copy()
    for col in columns:
        draw_animated_pillar(
            final_frame,
            col["cx"],
            cy_base,
            rx,
            ry,
            col["target_h"],
            col,
            1.0,
        )
    final_frame.alpha_composite(
        cached_box_with_glow,
        (target_box_x - pad, target_box_y - pad),
    )
    final_bgr = cv2.cvtColor(
        np.array(final_frame.convert("RGB")), cv2.COLOR_RGB2BGR
    )
    final_bytes = final_bgr.tobytes()

    for i in range(ANIM_FRAMES, TOTAL_FRAMES):
        write_frame_bytes(final_bytes)

    if ffmpeg_proc:
        ffmpeg_proc.stdin.close()
        ffmpeg_proc.wait()
    elif cv_writer:
        cv_writer.release()

    elapsed = time.time() - start_time
    print(f"\n\n✅ Done in {elapsed:.2f}s | Path:\n{output_video_path}\n")
    return output_video_path


if __name__ == "__main__":
    main()
