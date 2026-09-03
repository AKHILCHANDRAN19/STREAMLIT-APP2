import datetime
import math
import os
import re
import subprocess
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import scrapping

# --- Physics Easing ---
def ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)

def clamp(val, min_v=0.0, max_v=1.0):
    return max(min_v, min(max_v, val))

# --- Gradient Polygon Renderer ---
def draw_gradient_poly(target_layer, pts, color_top, color_bottom):
    pts_arr = np.float32(pts)
    min_x = max(0, int(np.min(pts_arr[:, 0])))
    max_x = min(target_layer.width, int(np.max(pts_arr[:, 0])) + 1)
    min_y = max(0, int(np.min(pts_arr[:, 1])))
    max_y = min(target_layer.height, int(np.max(pts_arr[:, 1])) + 1)

    bw = max_x - min_x
    bh = max_y - min_y
    if bw <= 0 or bh <= 0:
        return

    pts_local = pts_arr.copy()
    pts_local[:, 0] -= min_x
    pts_local[:, 1] -= min_y

    mask = np.zeros((bh, bw), dtype=np.uint8)
    cv2.fillPoly(mask, [np.int32(pts_local)], 255)

    y_idx = np.arange(bh, dtype=np.float32)
    t = np.clip(y_idx / max(1.0, float(bh - 1)), 0.0, 1.0)[:, None]

    c_top = np.array(color_top, dtype=np.float32)
    c_bot = np.array(color_bottom, dtype=np.float32)
    row_colors = (1.0 - t) * c_top + t * c_bot

    grad_arr = np.tile(row_colors[:, None, :], (1, bw, 1))
    grad_img = Image.fromarray(np.uint8(grad_arr), mode='RGB').convert('RGBA')
    mask_img = Image.fromarray(mask, mode='L')

    target_layer.paste(grad_img, (min_x, min_y), mask_img)

# --- Perspective Date Precomputation ---
def precompute_date_overlay(pts_dst, day, month, year, f_day, f_month, f_year, W, H):
    tw, th = 560, 720
    txt_img = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(txt_img)

    b1 = t_draw.textbbox((0, 0), day, font=f_day)
    t_draw.text(((tw - (b1[2] - b1[0])) / 2, 16), day, fill=(255, 255, 255, 255), font=f_day)

    b2 = t_draw.textbbox((0, 0), month, font=f_month)
    t_draw.text(((tw - (b2[2] - b2[0])) / 2, 220), month, fill=(255, 255, 255, 255), font=f_month)

    b3 = t_draw.textbbox((0, 0), year, font=f_year)
    t_draw.text(((tw - (b3[2] - b3[0])) / 2, 420), year, fill=(255, 255, 255, 255), font=f_year)

    src_pts = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])
    dst_pts = np.float32(pts_dst)

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(
        np.array(txt_img), M, (W, H),
        flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)
    )
    return Image.fromarray(warped, mode='RGBA')

def fetch_and_prepare_dataset():
    gr_data = scrapping.scrape_goodreturns_22k()
    history = gr_data.get("history", [])
    now = datetime.datetime.now()

    if not history or len(history) < 2:
        return [
            {"day": "26", "month": "AUG", "year": "2026", "price_int": 15010, "change": "₹0", "chg_type": "neutral", "target_h": 340.0, "badge": "WEEK HIGH"},
            {"day": "27", "month": "AUG", "year": "2026", "price_int": 14725, "change": "-₹285", "chg_type": "down", "target_h": 295.0, "badge": None},
            {"day": "28", "month": "AUG", "year": "2026", "price_int": 14770, "change": "+₹45", "chg_type": "up", "target_h": 302.0, "badge": None},
            {"day": "29", "month": "AUG", "year": "2026", "price_int": 14505, "change": "-₹265", "chg_type": "down", "target_h": 260.0, "badge": None},
            {"day": "30", "month": "AUG", "year": "2026", "price_int": 14505, "change": "₹0", "chg_type": "neutral", "target_h": 260.0, "badge": None},
            {"day": "31", "month": "AUG", "year": "2026", "price_int": 14370, "change": "-₹135", "chg_type": "down", "target_h": 235.0, "badge": None},
            {"day": "01", "month": "SEP", "year": "2026", "price_int": 14125, "change": "-₹245", "chg_type": "down", "target_h": 195.0, "badge": "WEEK LOW"}
        ]

    raw_past = history[1:9]
    raw_slice = list(reversed(raw_past))
    work_slice = raw_slice[1:] if len(raw_slice) == 8 else raw_slice
    has_prev = (len(raw_slice) == 8)

    prices = [int(item['1g']) for item in work_slice]
    min_p, max_p = min(prices), max(prices)
    high_idx = prices.index(max_p)
    low_idx = prices.index(min_p)

    dataset = []
    for i, item in enumerate(work_slice):
        date_str = item['date'].replace(" (Today)", "").strip()
        day_match = re.search(r'\d+', date_str)
        month_match = re.search(r'[a-zA-Z]+', date_str)

        day_txt = f"{int(day_match.group()):02d}" if day_match else f"{now.day:02d}"
        month_txt = month_match.group().upper()[:3] if month_match else "AUG"
        year_txt = str(now.year)

        p_curr = prices[i]
        diff = (p_curr - int(raw_slice[i]['1g'])) if has_prev else (0 if i == 0 else p_curr - prices[i - 1])

        if diff > 0:
            chg_str, chg_type = f"+₹{abs(diff)}", "up"
        elif diff < 0:
            chg_str, chg_type = f"-₹{abs(diff)}", "down"
        else:
            chg_str, chg_type = "₹0", "neutral"

        target_h = 195.0 + ((p_curr - min_p) / float(max_p - min_p)) * 145.0 if max_p > min_p else 260.0
        badge = "WEEK HIGH" if i == high_idx else ("WEEK LOW" if i == low_idx else None)

        dataset.append({
            "day": day_txt, "month": month_txt, "year": year_txt,
            "price_int": p_curr, "change": chg_str, "chg_type": chg_type,
            "target_h": float(target_h), "badge": badge
        })

    return dataset

def generate_perfect_fast_animation(duration_sec=None, output_override=None):
    W, H = 1920, 1080
    FPS = 30
    TOTAL_FRAMES = max(int(FPS * duration_sec), 150) if duration_sec else 180

    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_paths = [
        os.path.join(base_dir, "Fonts", "Roboto-Bold.ttf"),
        os.path.join(base_dir, "Fonts", "Montserrat-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/system/fonts/Roboto-Bold.ttf"
    ]
    font_path = next((p for p in font_paths if os.path.exists(p)), None)

    def load_font(size):
        if font_path:
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    font_title   = load_font(52)
    font_sub     = load_font(22)
    font_price   = load_font(44)
    font_change  = load_font(20)
    font_badge   = load_font(18)

    f_bar_day   = load_font(152)
    f_bar_month = load_font(116)
    f_bar_year  = load_font(108)

    data = fetch_and_prepare_dataset()

    u_left   = np.array([-80.0, -25.0])
    v_right  = np.array([85.0, -22.0])
    step_vec = np.array([215.0, -42.0])
    base_origin = np.array([320.0, 970.0])
    bases = [base_origin + i * step_vec for i in range(7)]

    col_top_light   = (58, 178, 255)
    col_top_dark    = (28, 145, 245)
    col_right_light = (0, 142, 248)
    col_right_dark  = (0, 108, 220)
    col_left_light  = (0, 112, 218)
    col_left_dark   = (0, 74, 175)

    line_blue  = (0, 108, 235, 255)
    color_down = (215, 45, 45, 255)
    color_up   = (30, 150, 60, 255)
    color_neu  = (120, 130, 145, 255)

    # 1. Background
    y_coords, x_coords = np.ogrid[:H, :W]
    cx, cy = W * 0.38, H * 0.45
    dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
    t_vignette = np.clip(dist / (np.sqrt(W**2 + H**2) * 0.65), 0.0, 1.0)
    bg_center = np.array([254, 255, 255], dtype=np.float32)
    bg_edge = np.array([214, 220, 230], dtype=np.float32)
    bg_arr = (1.0 - t_vignette[:, :, None]) * bg_center + t_vignette[:, :, None] * bg_edge

    static_bg = Image.fromarray(np.uint8(bg_arr), mode='RGB').convert('RGBA')
    h_draw = ImageDraw.Draw(static_bg)
    h_draw.text((80, 60), "22K PRICE COMPARISON", fill=(0, 108, 235, 255), font=font_title)
    desc = f"Last 7 Days Gold Rate Trend (per gram) • Kerala, India\nPeriod: {data[0]['month'].capitalize()} {data[0]['day']}, {data[0]['year']} - {data[-1]['month'].capitalize()} {data[-1]['day']}, {data[-1]['year']}"
    h_draw.multiline_text((80, 128), desc, fill=(105, 115, 130, 255), font=font_sub, spacing=8)

    # 2. Pre-bake Shadows
    individual_shadows = []
    for i in range(7):
        b = bases[i]
        sh_img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(sh_img)
        s_draw.polygon([tuple(p) for p in [b + u_left, b, b + v_right, b + u_left + v_right]], fill=(20, 35, 60, 90))
        s_draw.ellipse([b[0] - 90, b[1] - 16, b[0] + 90, b[1] + 18], fill=(30, 45, 75, 70))
        min_x, max_x = max(0, int(b[0] - 120)), min(W, int(b[0] + 120))
        min_y, max_y = max(0, int(b[1] - 45)), min(H, int(b[1] + 45))
        individual_shadows.append((sh_img.crop((min_x, min_y, max_x, max_y)).filter(ImageFilter.GaussianBlur(radius=10)), (min_x, min_y)))

    # 3. Pre-bake Dates
    precomputed_dates = []
    for i in range(7):
        b = bases[i]
        p_bl = b + 0.08 * v_right - np.array([0.0, 14.0])
        p_br = b + 0.92 * v_right - np.array([0.0, 14.0])
        layer = precompute_date_overlay(
            [p_bl - np.array([0.0, 140.0]), p_br - np.array([0.0, 140.0]), p_br, p_bl],
            data[i]["day"], data[i]["month"], data[i]["year"],
            f_bar_day, f_bar_month, f_bar_year, W, H
        )
        precomputed_dates.append(layer)

    # 4. Pre-bake Sprites & Reflections
    BAR_DUR = 24
    LINE_DUR = 14
    cached_bar_sprites = [[] for _ in range(7)]
    individual_reflections = []

    for i in range(7):
        b = bases[i]
        for step in range(BAR_DUR + 1):
            h = max(0.0, data[i]["target_h"] * ease_out_back(step / float(BAR_DUR)))
            p0, p1, p2, p3 = b, b + v_right, b + u_left + v_right, b + u_left
            p4, p5, p6, p7 = p0 - np.array([0.0, h]), p1 - np.array([0.0, h]), p2 - np.array([0.0, h]), p3 - np.array([0.0, h])
            top_center = (p4 + p5 + p6 + p7) / 4.0

            bar_img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            draw_gradient_poly(bar_img, [p3, p0, p4, p7], col_left_light, col_left_dark)
            draw_gradient_poly(bar_img, [p0, p1, p5, p4], col_right_light, col_right_dark)
            draw_gradient_poly(bar_img, [p4, p5, p6, p7], col_top_light, col_top_dark)

            b_draw = ImageDraw.Draw(bar_img)
            b_draw.line([tuple(p7), tuple(p4), tuple(p5)], fill=(130, 220, 255, 220), width=2)
            b_draw.line([tuple(p4), tuple(p0)], fill=(80, 185, 255, 160), width=2)

            if h >= 80.0:
                d_alpha = clamp((h - 80.0) / 120.0)
                if d_alpha > 0.0:
                    txt_layer = precomputed_dates[i]
                    if d_alpha < 1.0:
                        arr = np.array(txt_layer)
                        arr[:, :, 3] = np.uint8(arr[:, :, 3] * d_alpha)
                        txt_layer = Image.fromarray(arr, mode='RGBA')
                    bar_img.alpha_composite(txt_layer)

            min_x, max_x = max(0, int(b[0] - 90)), min(W, int(b[0] + 95))
            min_y, max_y = max(0, int(p6[1] - 5)), int(b[1] + 2)
            cached_bar_sprites[i].append((bar_img.crop((min_x, min_y, max_x, max_y)), (min_x, min_y), top_center))

        full_patch, (fx, fy), _ = cached_bar_sprites[i][-1]
        temp_l = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        temp_l.paste(full_patch, (fx, fy))
        rx1, rx2, base_y = max(0, int(b[0] - 90)), min(W, int(b[0] + 95)), int(b[1])
        flipped = temp_l.crop((rx1, base_y - 80, rx2, base_y)).transpose(Image.FLIP_TOP_BOTTOM)
        fw, fh = flipped.size
        fade = np.zeros((fh, fw), dtype=np.uint8)
        for y_i in range(fh):
            fade[y_i, :] = max(0, int(50 * (1.0 - (y_i / float(fh)) ** 0.55)))
        flipped.putalpha(Image.fromarray(fade, mode='L'))
        individual_reflections.append((flipped.filter(ImageFilter.GaussianBlur(radius=2)), (rx1, base_y + 1)))

    output_path = output_override or os.path.join(base_dir, "Videos", "sevenday_comparison.mp4")
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
        '-s', f'{W}x{H}', '-pix_fmt', 'bgr24', '-r', str(FPS),
        '-i', '-', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-crf', '22', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', output_path
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # 5. Continuous Rendering Loop
    for frame in range(TOTAL_FRAMES):
        canvas = static_bg.copy()

        # Shadows & Reflections
        for i in range(7):
            sf = 8 + i * 9
            if frame >= sf:
                p_bar = clamp((frame - sf) / float(BAR_DUR))
                sh_patch, sh_pos = individual_shadows[i]
                if p_bar < 0.9:
                    arr = np.array(sh_patch)
                    arr[:, :, 3] = np.uint8(arr[:, :, 3] * clamp(p_bar * 1.4))
                    canvas.paste(Image.fromarray(arr, mode='RGBA'), sh_pos, Image.fromarray(arr, mode='RGBA'))
                else:
                    canvas.paste(sh_patch, sh_pos, sh_patch)

            if frame >= sf + 5:
                p_refl = clamp((frame - (sf + 5)) / float(BAR_DUR - 5))
                rf_patch, rf_pos = individual_reflections[i]
                if p_refl < 0.95:
                    arr = np.array(rf_patch)
                    arr[:, :, 3] = np.uint8(arr[:, :, 3] * p_refl)
                    canvas.paste(Image.fromarray(arr, mode='RGBA'), rf_pos, Image.fromarray(arr, mode='RGBA'))
                else:
                    canvas.paste(rf_patch, rf_pos, rf_patch)

        # 3D Bars
        top_centers = [None] * 7
        for i in reversed(range(7)):
            sf = 8 + i * 9
            if frame >= sf:
                step_idx = min(BAR_DUR, frame - sf)
                patch, pos, tc = cached_bar_sprites[i][step_idx]
                canvas.paste(patch, pos, patch)
                top_centers[i] = tc

        # Continuously Looping Flowing Light Node & Spline
        if frame > 70:
            trend_a = int(220 * clamp((frame - 70) / 20.0))
            active_pts = [tc for tc in top_centers if tc is not None]
            if len(active_pts) >= 2:
                tr_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                tr_draw = ImageDraw.Draw(tr_layer)
                tr_draw.line([tuple(p) for p in active_pts], fill=(0, 180, 255, trend_a), width=3)

                # Continuous infinite loop across full audio duration
                pulse_t = ((frame - 70) * 0.04) % 1.0
                p_idx = int(pulse_t * (len(active_pts) - 1))
                if p_idx < len(active_pts) - 1:
                    sub_t = (pulse_t * (len(active_pts) - 1)) - p_idx
                    pp = active_pts[p_idx] * (1.0 - sub_t) + active_pts[p_idx + 1] * sub_t
                    tr_draw.ellipse([pp[0]-9, pp[1]-9, pp[0]+9, pp[1]+9], fill=(255, 255, 255, trend_a))
                    tr_draw.ellipse([pp[0]-16, pp[1]-16, pp[0]+16, pp[1]+16], outline=(100, 220, 255, int(trend_a * 0.5)), width=2)

                canvas.alpha_composite(tr_layer)

        # Dynamic Callout Lines & Counter
        callout_draw = ImageDraw.Draw(canvas)
        for i in range(7):
            tc = top_centers[i]
            if tc is None:
                continue

            lsf = 8 + i * 9 + 12
            p_line = clamp((frame - lsf) / float(LINE_DUR))
            if p_line <= 0:
                continue

            pt_start = (tc[0], tc[1] - 4)
            pt_elbow = (tc[0] - 65, tc[1] - 70)
            pt_end   = (pt_elbow[0] - 100, pt_elbow[1])

            if p_line <= 0.5:
                t_seg = p_line / 0.5
                curr_pt = (pt_start[0] + t_seg * (pt_elbow[0] - pt_start[0]), pt_start[1] + t_seg * (pt_elbow[1] - pt_start[1]))
                callout_draw.line([pt_start, curr_pt], fill=line_blue, width=3)
                callout_draw.ellipse([curr_pt[0]-4, curr_pt[1]-4, curr_pt[0]+4, curr_pt[1]+4], fill=(255, 255, 255, 255))
            else:
                callout_draw.line([pt_start, pt_elbow], fill=line_blue, width=3)
                t_seg = (p_line - 0.5) / 0.5
                curr_pt = (pt_elbow[0] + t_seg * (pt_end[0] - pt_elbow[0]), pt_elbow[1])
                callout_draw.line([pt_elbow, curr_pt], fill=line_blue, width=3)
                callout_draw.ellipse([curr_pt[0]-4, curr_pt[1]-4, curr_pt[0]+4, curr_pt[1]+4], fill=(255, 255, 255, 255))

            if p_line >= 0.6:
                text_t = (p_line - 0.6) / 0.4
                curr_val = int(10000 + (data[i]["price_int"] - 10000) * text_t)
                txt_alpha = int(255 * text_t)
                callout_draw.text((pt_end[0], pt_elbow[1] - 52), f"₹{curr_val:,}", fill=(0, 108, 235, txt_alpha), font=font_price)
                c_color = color_down if data[i]["chg_type"] == "down" else (color_up if data[i]["chg_type"] == "up" else color_neu)
                callout_draw.text((pt_end[0] + 4, pt_elbow[1] + 8), f"({data[i]['change']})", fill=(c_color[0], c_color[1], c_color[2], txt_alpha), font=font_change)

        # Continuous Pulsing Badges Throughout Video
        if frame > 90:
            badge_alpha = int(255 * clamp((frame - 90) / 15.0))
            badge_pulse = math.sin((frame - 90) * 0.12) * 3.5

            for idx in [i for i in range(7) if data[i]["badge"] is not None]:
                tc = top_centers[idx]
                if tc is not None:
                    badge_txt = data[idx]["badge"]
                    b_color = (235, 140, 0, badge_alpha) if badge_txt == "WEEK HIGH" else (210, 45, 45, badge_alpha)
                    bx = tc[0] - (120 if badge_txt == "WEEK LOW" else 130)
                    by = tc[1] - 170 + badge_pulse

                    halo_pad = 2.0 + math.sin((frame - 90) * 0.15) * 2.0
                    callout_draw.rounded_rectangle([bx - halo_pad, by - halo_pad, bx + 115 + halo_pad, by + 28 + halo_pad], radius=8, fill=(b_color[0], b_color[1], b_color[2], int(badge_alpha * 0.35)))
                    callout_draw.rounded_rectangle([bx, by, bx + 115, by + 28], radius=6, fill=b_color)
                    callout_draw.text((bx + 8, by + 4), badge_txt, fill=(255, 255, 255, badge_alpha), font=font_badge)

        frame_bgr = cv2.cvtColor(np.array(canvas.convert('RGB')), cv2.COLOR_RGB2BGR)
        proc.stdin.write(frame_bgr.tobytes())

    proc.stdin.close()
    proc.wait()
    return output_path

def main(duration_sec=None):
    return generate_perfect_fast_animation(duration_sec=duration_sec)

if __name__ == "__main__":
    main()
