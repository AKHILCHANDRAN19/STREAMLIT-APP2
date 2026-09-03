import os
import math
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import cv2
import datetime
import re
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

# --- Razor-Sharp Perspective Date Precomputation ---
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
    """Fetches real 7-day data from GoodReturns and builds dynamic metadata."""
    gr_data = scrapping.scrape_goodreturns_22k()
    history = gr_data.get("history", [])
    now = datetime.datetime.now()

    # Fallback to mock dataset if history is unavailable
    if not history:
        return [
            {"day": "26", "month": "AUG", "year": "2026", "price_int": 15010, "change": "₹0", "chg_type": "neutral", "target_h": 340.0, "badge": "WEEK HIGH"},
            {"day": "27", "month": "AUG", "year": "2026", "price_int": 14725, "change": "-₹285", "chg_type": "down", "target_h": 295.0, "badge": None},
            {"day": "28", "month": "AUG", "year": "2026", "price_int": 14770, "change": "+₹45", "chg_type": "up", "target_h": 302.0, "badge": None},
            {"day": "29", "month": "AUG", "year": "2026", "price_int": 14505, "change": "-₹265", "chg_type": "down", "target_h": 260.0, "badge": None},
            {"day": "30", "month": "AUG", "year": "2026", "price_int": 14505, "change": "₹0", "chg_type": "neutral", "target_h": 260.0, "badge": None},
            {"day": "31", "month": "AUG", "year": "2026", "price_int": 14370, "change": "-₹135", "chg_type": "down", "target_h": 235.0, "badge": None},
            {"day": "01", "month": "SEP", "year": "2026", "price_int": 14125, "change": "-₹245", "chg_type": "down", "target_h": 195.0, "badge": "WEEK LOW"}
        ]

    # Use up to 8 entries to calculate previous-day differences for all 7 days
    raw_slice = list(reversed(history[:8]))
    if len(raw_slice) >= 8:
        work_slice = raw_slice[1:]
        has_prev = True
    else:
        work_slice = raw_slice
        has_prev = False

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
        if has_prev:
            p_prev = int(raw_slice[i]['1g'])
            diff = p_curr - p_prev
        else:
            diff = 0 if i == 0 else p_curr - prices[i - 1]

        if diff > 0:
            chg_str = f"+₹{abs(diff)}"
            chg_type = "up"
        elif diff < 0:
            chg_str = f"-₹{abs(diff)}"
            chg_type = "down"
        else:
            chg_str = "₹0"
            chg_type = "neutral"

        # Dynamically scale bar height between 195.0 and 340.0
        if max_p > min_p:
            target_h = 195.0 + ((p_curr - min_p) / float(max_p - min_p)) * 145.0
        else:
            target_h = 260.0

        # Dynamic badge allocation
        if i == high_idx:
            badge = "WEEK HIGH"
        elif i == low_idx:
            badge = "WEEK LOW"
        else:
            badge = None

        dataset.append({
            "day": day_txt,
            "month": month_txt,
            "year": year_txt,
            "price_int": p_curr,
            "change": chg_str,
            "chg_type": chg_type,
            "target_h": float(target_h),
            "badge": badge
        })

    return dataset

def generate_perfect_fast_animation(output_override=None):
    W, H = 1920, 1080
    FPS = 60
    TOTAL_FRAMES = 330  # 5.5 Seconds

    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_paths = [
        os.path.join(base_dir, "Fonts", "Roboto-Bold.ttf"),
        os.path.join(base_dir, "Fonts", "Montserrat-Bold.ttf"),
        os.path.join(base_dir, "Fonts", "Montserrat-ExtraBold.ttf"),
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

    # Load Real Scraped Dataset
    data = fetch_and_prepare_dataset()

    # 3D Vector Geometry
    u_left   = np.array([-80.0, -25.0])
    v_right  = np.array([85.0, -22.0])
    step_vec = np.array([215.0, -42.0])
    base_origin = np.array([320.0, 970.0])
    bases = [base_origin + i * step_vec for i in range(7)]

    # Colors
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

    print("\n[PRE-BAKING] Pre-computing individual dynamic assets...")

    # 1. Static Studio Background with Header
    y_coords, x_coords = np.ogrid[:H, :W]
    cx, cy = W * 0.38, H * 0.45
    dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
    max_dist = np.sqrt(W**2 + H**2) * 0.65
    t_vignette = np.clip(dist / max_dist, 0.0, 1.0)
    bg_center = np.array([254, 255, 255], dtype=np.float32)
    bg_edge = np.array([214, 220, 230], dtype=np.float32)
    bg_arr = (1.0 - t_vignette[:, :, None]) * bg_center + t_vignette[:, :, None] * bg_edge

    static_bg = Image.fromarray(np.uint8(bg_arr), mode='RGB').convert('RGBA')
    h_draw = ImageDraw.Draw(static_bg)
    h_draw.text((80, 60), "22K PRICE COMPARISON", fill=(0, 108, 235, 255), font=font_title)
    
    start_dt = f"{data[0]['month'].capitalize()} {data[0]['day']}, {data[0]['year']}"
    end_dt = f"{data[-1]['month'].capitalize()} {data[-1]['day']}, {data[-1]['year']}"
    desc = f"Last 7 Days Gold Rate Trend (per gram) • Kerala, India\nPeriod: {start_dt} - {end_dt}"
    h_draw.multiline_text((80, 128), desc, fill=(105, 115, 130, 255), font=font_sub, spacing=8)

    # 2. Pre-bake Individual Shadow Patches
    individual_shadows = []
    for i in range(7):
        b = bases[i]
        min_x = max(0, int(b[0] - 120))
        max_x = min(W, int(b[0] + 120))
        min_y = max(0, int(b[1] - 45))
        max_y = min(H, int(b[1] + 45))

        sh_img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(sh_img)
        poly_base = [b + u_left, b, b + v_right, b + u_left + v_right]
        s_draw.polygon([tuple(p) for p in poly_base], fill=(20, 35, 60, 90))
        s_draw.ellipse([b[0] - 90, b[1] - 16, b[0] + 90, b[1] + 18], fill=(30, 45, 75, 70))

        cropped_sh = sh_img.crop((min_x, min_y, max_x, max_y)).filter(ImageFilter.GaussianBlur(radius=10))
        individual_shadows.append((cropped_sh, (min_x, min_y)))

    # 3. Pre-bake 3D Perspective Date Cards
    precomputed_dates = []
    for i in range(7):
        b = bases[i]
        p_bl = b + 0.08 * v_right - np.array([0.0, 14.0])
        p_br = b + 0.92 * v_right - np.array([0.0, 14.0])
        p_tl = p_bl - np.array([0.0, 140.0])
        p_tr = p_br - np.array([0.0, 140.0])

        layer = precompute_date_overlay(
            [p_tl, p_tr, p_br, p_bl],
            data[i]["day"], data[i]["month"], data[i]["year"],
            f_bar_day, f_bar_month, f_bar_year, W, H
        )
        precomputed_dates.append(layer)

    # 4. Pre-bake Growth Steps & Dynamic Reflections
    BAR_DUR = 45
    LINE_DUR = 25

    cached_bar_sprites = [[] for _ in range(7)]
    individual_reflections = []

    for i in range(7):
        b = bases[i]
        for step in range(BAR_DUR + 1):
            t_bar = step / float(BAR_DUR)
            h = max(0.0, data[i]["target_h"] * ease_out_back(t_bar))

            p0 = b
            p1 = b + v_right
            p2 = b + u_left + v_right
            p3 = b + u_left
            p4 = p0 - np.array([0.0, h])
            p5 = p1 - np.array([0.0, h])
            p6 = p2 - np.array([0.0, h])
            p7 = p3 - np.array([0.0, h])

            top_center = (p4 + p5 + p6 + p7) / 4.0

            min_x = max(0, int(b[0] - 90))
            max_x = min(W, int(b[0] + 95))
            min_y = max(0, int(p6[1] - 5))
            max_y = int(b[1] + 2)

            bar_img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            draw_gradient_poly(bar_img, [p3, p0, p4, p7], col_left_light, col_left_dark)
            draw_gradient_poly(bar_img, [p0, p1, p5, p4], col_right_light, col_right_dark)
            draw_gradient_poly(bar_img, [p4, p5, p6, p7], col_top_light, col_top_dark)

            b_draw = ImageDraw.Draw(bar_img)
            b_draw.line([tuple(p7), tuple(p4), tuple(p5)], fill=(130, 220, 255, 220), width=2)
            b_draw.line([tuple(p4), tuple(p0)], fill=(80, 185, 255, 160), width=2)
            b_draw.line([tuple(p0), tuple(p1)], fill=(0, 75, 165, 120), width=1)
            b_draw.line([tuple(p0), tuple(p3)], fill=(0, 60, 140, 120), width=1)

            if h >= 80.0:
                d_alpha = clamp((h - 80.0) / 120.0)
                if d_alpha > 0.0:
                    txt_layer = precomputed_dates[i]
                    if d_alpha < 1.0:
                        arr = np.array(txt_layer)
                        arr[:, :, 3] = np.uint8(arr[:, :, 3] * d_alpha)
                        txt_layer = Image.fromarray(arr, mode='RGBA')
                    bar_img.alpha_composite(txt_layer)

            crop_patch = bar_img.crop((min_x, min_y, max_x, max_y))
            cached_bar_sprites[i].append((crop_patch, (min_x, min_y), top_center))

        full_patch, (fx, fy), _ = cached_bar_sprites[i][-1]
        base_y = int(b[1])
        crop_h = 80
        rx1 = max(0, int(b[0] - 90))
        rx2 = min(W, int(b[0] + 95))

        temp_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        temp_layer.paste(full_patch, (fx, fy))

        cropped_bar = temp_layer.crop((rx1, base_y - crop_h, rx2, base_y))
        flipped = cropped_bar.transpose(Image.FLIP_TOP_BOTTOM)
        f_w, f_h = flipped.size
        fade = np.zeros((f_h, f_w), dtype=np.uint8)
        for y_i in range(f_h):
            fade[y_i, :] = max(0, int(50 * (1.0 - (y_i / float(f_h)) ** 0.55)))
        flipped.putalpha(Image.fromarray(fade, mode='L'))
        flipped = flipped.filter(ImageFilter.GaussianBlur(radius=2))

        individual_reflections.append((flipped, (rx1, base_y + 1)))

    # Output Destination
    if output_override:
        output_path = output_override
    else:
        out_dir = os.path.join(base_dir, "Videos")
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, "sevenday_comparison.mp4")

    ffmpeg_cmd = [
        'ffmpeg',
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{W}x{H}',
        '-pix_fmt', 'bgr24',
        '-r', str(FPS),
        '-i', '-',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'fastdecode',
        '-crf', '19',
        '-threads', '2',
        '-pix_fmt', 'yuv420p',
        output_path
    ]

    try:
        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("[ERROR] FFmpeg is not found.")
        return output_path

    # Main Realtime Blitting Loop
    for frame in range(TOTAL_FRAMES):
        canvas = static_bg.copy()

        # 1. Dynamic Contact Shadows
        for i in range(7):
            start_f = 15 + i * 18
            if frame >= start_f:
                p_bar = clamp((frame - start_f) / float(BAR_DUR))
                sh_alpha = clamp(p_bar * 1.4)

                sh_patch, sh_pos = individual_shadows[i]
                if sh_alpha < 1.0:
                    arr = np.array(sh_patch)
                    arr[:, :, 3] = np.uint8(arr[:, :, 3] * sh_alpha)
                    canvas.paste(Image.fromarray(arr, mode='RGBA'), sh_pos, Image.fromarray(arr, mode='RGBA'))
                else:
                    canvas.paste(sh_patch, sh_pos, sh_patch)

        # 2. Dynamic Reflections
        for i in range(7):
            start_f = 15 + i * 18
            if frame >= start_f + 10:
                p_refl = clamp((frame - (start_f + 10)) / float(BAR_DUR - 10))
                refl_patch, refl_pos = individual_reflections[i]
                if p_refl < 1.0:
                    arr = np.array(refl_patch)
                    arr[:, :, 3] = np.uint8(arr[:, :, 3] * p_refl)
                    canvas.paste(Image.fromarray(arr, mode='RGBA'), refl_pos, Image.fromarray(arr, mode='RGBA'))
                else:
                    canvas.paste(refl_patch, refl_pos, refl_patch)

        # 3. 3D Bars (Back-to-Front Order: 7 -> 1)
        top_centers = [None] * 7
        for i in reversed(range(7)):
            start_f = 15 + i * 18
            if frame >= start_f:
                step_idx = min(BAR_DUR, frame - start_f)
                patch, pos, tc = cached_bar_sprites[i][step_idx]
                canvas.paste(patch, pos, patch)
                top_centers[i] = tc

        # 4. Connecting Glowing Spline & Flowing Light Pulse
        if frame > 140:
            trend_alpha = int(220 * clamp((frame - 140) / 40.0))
            active_pts = [tc for tc in top_centers if tc is not None]
            if len(active_pts) >= 2:
                trend_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                tr_draw = ImageDraw.Draw(trend_layer)

                curve_pts = [tuple(p) for p in active_pts]
                tr_draw.line(curve_pts, fill=(0, 180, 255, trend_alpha), width=3)

                pulse_t = ((frame - 140) * 0.05) % 1.0
                pulse_idx = int(pulse_t * (len(active_pts) - 1))
                if pulse_idx < len(active_pts) - 1:
                    pA = active_pts[pulse_idx]
                    pB = active_pts[pulse_idx + 1]
                    sub_t = (pulse_t * (len(active_pts) - 1)) - pulse_idx
                    pulse_pos = pA * (1.0 - sub_t) + pB * sub_t
                    tr_draw.ellipse([pulse_pos[0]-8, pulse_pos[1]-8, pulse_pos[0]+8, pulse_pos[1]+8], fill=(255, 255, 255, trend_alpha))

                canvas.alpha_composite(trend_layer)

        # 5. Progressive Callouts & Digital Price Ticker
        callout_draw = ImageDraw.Draw(canvas)
        for i in range(7):
            tc = top_centers[i]
            if tc is None:
                continue

            line_start_f = 15 + i * 18 + 25
            p_line = clamp((frame - line_start_f) / float(LINE_DUR))
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
                price_str = f"₹{curr_val:,}"

                txt_alpha = int(255 * text_t)
                callout_draw.text((pt_end[0], pt_elbow[1] - 52), price_str, fill=(0, 108, 235, txt_alpha), font=font_price)

                c_color = color_down if data[i]["chg_type"] == "down" else (color_up if data[i]["chg_type"] == "up" else color_neu)
                c_color_a = (c_color[0], c_color[1], c_color[2], txt_alpha)
                callout_draw.text((pt_end[0] + 4, pt_elbow[1] + 8), f"({data[i]['change']})", fill=c_color_a, font=font_change)

        # 6. Week High / Low Badges (Dynamic to actual High & Low indices)
        if frame > 200:
            badge_alpha = int(255 * clamp((frame - 200) / 30.0))
            pulse = math.sin((frame - 200) * 0.15) * 3.0

            badge_indices = [idx for idx in range(7) if data[idx]["badge"] is not None]
            for i in badge_indices:
                tc = top_centers[i]
                if tc is not None:
                    badge_txt = data[i]["badge"]
                    b_color = (235, 140, 0, badge_alpha) if badge_txt == "WEEK HIGH" else (210, 45, 45, badge_alpha)

                    bx = tc[0] - 120 if badge_txt == "WEEK LOW" else tc[0] - 130
                    by = tc[1] - 170 + pulse
                    callout_draw.rounded_rectangle([bx, by, bx + 115, by + 28], radius=6, fill=b_color)
                    callout_draw.text((bx + 8, by + 4), badge_txt, fill=(255, 255, 255, badge_alpha), font=font_badge)

        # Stream Frame to FFmpeg
        frame_rgb = canvas.convert('RGB')
        frame_bgr = cv2.cvtColor(np.array(frame_rgb), cv2.COLOR_RGB2BGR)
        ffmpeg_proc.stdin.write(frame_bgr.tobytes())

    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()
    return output_path

def main():
    return generate_perfect_fast_animation()

if __name__ == "__main__":
    main()
