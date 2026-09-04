import os
import math
import subprocess
import wave
import gc
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import cv2
import datetime
import re
import scrapping

# ==========================================
# CONFIGURATION & REPO PATHS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
AUDIOS_DIR = os.path.join(BASE_DIR, "Audios")
FONTS_DIR = os.path.join(BASE_DIR, "Fonts")

os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(AUDIOS_DIR, exist_ok=True)

SFX_PATH = os.path.join(AUDIOS_DIR, "comp_sfx.wav")

def ease_out_back(t, c1=1.70158):
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)

def clamp(val, min_v=0.0, max_v=1.0):
    return max(min_v, min(max_v, val))

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

        if max_p > min_p:
            target_h = 195.0 + ((p_curr - min_p) / float(max_p - min_p)) * 145.0
        else:
            target_h = 260.0

        if i == high_idx:
            badge = "WEEK HIGH"
        elif i == low_idx:
            badge = "WEEK LOW"
        else:
            badge = None

        dataset.append({
            "day": day_txt, "month": month_txt, "year": year_txt,
            "price_int": p_curr, "change": chg_str, "chg_type": chg_type,
            "target_h": float(target_h), "badge": badge
        })

    return dataset

# ==========================================
# PROCEDURAL AUDIO SYNTHESIZER
# ==========================================
def synthesize_comparison_sfx(output_path, total_duration, sample_rate=44100):
    total_samples = int(total_duration * sample_rate)
    left = np.zeros(total_samples, dtype=np.float32)
    right = np.zeros(total_samples, dtype=np.float32)

    # 1. Riser sweep (0.2s - 2.5s)
    t_rise = np.linspace(0, 2.3, int(sample_rate * 2.3), endpoint=False)
    freq_rise = np.linspace(220.0, 680.0, len(t_rise))
    phase_rise = 2.0 * np.pi * np.cumsum(freq_rise) / sample_rate
    shimmer = np.sin(phase_rise) * np.exp(-t_rise * 0.8) * 0.18

    # 2. Spline Bell Chime (at t = 2.5s)
    t_bell = np.linspace(0, 1.4, int(sample_rate * 1.4), endpoint=False)
    bell = (np.sin(2.0 * np.pi * 1046.5 * t_bell) * 0.4 + np.sin(2.0 * np.pi * 1568.0 * t_bell) * 0.25) * np.exp(-t_bell * 3.2) * 0.4

    # 3. Ambient Pad
    t_pad = np.linspace(0, total_duration, total_samples, endpoint=False)
    pad = (np.sin(2.0 * np.pi * 110.0 * t_pad) * 0.08 + np.sin(2.0 * np.pi * 164.81 * t_pad) * 0.05)

    idx_rise = int(0.2 * sample_rate)
    left[idx_rise:idx_rise + len(shimmer)] += shimmer
    right[idx_rise:idx_rise + len(shimmer)] += shimmer

    idx_bell = int(2.5 * sample_rate)
    if idx_bell + len(bell) < total_samples:
        left[idx_bell:idx_bell + len(bell)] += bell
        right[idx_bell:idx_bell + len(bell)] += bell

    left += pad
    right += pad

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
# MASTER GRAPHICS ENGINE
# ==========================================
def generate_perfect_fast_animation(duration_sec=None, output_override=None):
    W, H = 1920, 1080
    FPS = 30

    effective_duration = float(duration_sec) if duration_sec and duration_sec > 1.0 else 7.5
    TOTAL_FRAMES = int(FPS * effective_duration)

    synthesize_comparison_sfx(SFX_PATH, total_duration=effective_duration)

    font_paths = [
        os.path.join(FONTS_DIR, "Montserrat-ExtraBold.ttf"),
        os.path.join(FONTS_DIR, "Montserrat-Bold.ttf"),
        os.path.join(FONTS_DIR, "Roboto-Bold.ttf"),
        "/system/fonts/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
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
    font_badge   = load_font(26)

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

    print(f"\n[Chart Engine] Rendering dynamic frames (Duration: {effective_duration:.1f}s | {TOTAL_FRAMES} frames)...")

    # Static Studio Background
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

    # Pre-bake Shadows & Perspective Dates
    individual_shadows = []
    precomputed_dates = []
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

        p_bl = b + 0.08 * v_right - np.array([0.0, 14.0])
        p_br = b + 0.92 * v_right - np.array([0.0, 14.0])
        p_tl = p_bl - np.array([0.0, 140.0])
        p_tr = p_br - np.array([0.0, 140.0])
        layer = precompute_date_overlay([p_tl, p_tr, p_br, p_bl], data[i]["day"], data[i]["month"], data[i]["year"], f_bar_day, f_bar_month, f_bar_year, W, H)
        precomputed_dates.append(layer)

    BAR_DUR = 25
    LINE_DUR = 15
    cached_bar_sprites = [[] for _ in range(7)]
    individual_reflections = []

    for i in range(7):
        b = bases[i]
        for step in range(BAR_DUR + 1):
            t_bar = step / float(BAR_DUR)
            h = max(0.0, data[i]["target_h"] * ease_out_back(t_bar, c1=1.4))

            p0, p1, p2, p3 = b, b + v_right, b + u_left + v_right, b + u_left
            p4, p5, p6, p7 = p0 - np.array([0.0, h]), p1 - np.array([0.0, h]), p2 - np.array([0.0, h]), p3 - np.array([0.0, h])
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
        rx1, rx2 = max(0, int(b[0] - 90)), min(W, int(b[0] + 95))

        temp_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        temp_layer.paste(full_patch, (fx, fy))
        cropped_bar = temp_layer.crop((rx1, base_y - crop_h, rx2, base_y)).transpose(Image.FLIP_TOP_BOTTOM)
        f_w, f_h = cropped_bar.size
        fade = np.zeros((f_h, f_w), dtype=np.uint8)
        for y_i in range(f_h):
            fade[y_i, :] = max(0, int(50 * (1.0 - (y_i / float(f_h)) ** 0.55)))
        cropped_bar.putalpha(Image.fromarray(fade, mode='L'))
        individual_reflections.append((cropped_bar.filter(ImageFilter.GaussianBlur(radius=2)), (rx1, base_y + 1)))

    output_path = output_override if output_override else os.path.join(VIDEOS_DIR, "sevenday_comparison.mp4")

    # STRICT 2-THREAD LIMIT & DIRECT RGB24 PIPE (Bypasses cv2.cvtColor entirely)
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-threads', '2',
        '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{W}x{H}',
        '-pix_fmt', 'rgb24', '-r', str(FPS), '-i', '-',
        '-i', SFX_PATH,
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'fastdecode', '-crf', '20',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '2',
        '-threads', '2', '-pix_fmt', 'yuv420p',
        '-t', str(effective_duration),
        '-movflags', '+faststart', output_path
    ]

    try:
        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("[ERROR] FFmpeg not found.")
        return output_path

    # ==================================================
    # MAIN LOOP (Optimized Direct Pipe + Memory Safe)
    # ==================================================
    for frame in range(TOTAL_FRAMES):
        canvas = static_bg.copy()

        # 1. Shadows (Your Exact Live Alpha Math Kept 100% Intact)
        for i in range(7):
            start_f = 8 + i * 9
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

        # 2. Reflections (Your Exact Live Alpha Math Kept 100% Intact)
        for i in range(7):
            start_f = 8 + i * 9
            if frame >= start_f + 5:
                p_refl = clamp((frame - (start_f + 5)) / float(BAR_DUR - 5))
                refl_patch, refl_pos = individual_reflections[i]
                if p_refl < 1.0:
                    arr = np.array(refl_patch)
                    arr[:, :, 3] = np.uint8(arr[:, :, 3] * p_refl)
                    canvas.paste(Image.fromarray(arr, mode='RGBA'), refl_pos, Image.fromarray(arr, mode='RGBA'))
                else:
                    canvas.paste(refl_patch, refl_pos, refl_patch)

        # 3. 3D Bars with Continuous Floating Breathing Pulse
        top_centers = [None] * 7
        for i in reversed(range(7)):
            start_f = 8 + i * 9
            if frame >= start_f:
                step_idx = min(BAR_DUR, frame - start_f)
                patch, pos, tc = cached_bar_sprites[i][step_idx]

                if frame > start_f + BAR_DUR:
                    bar_pulse = math.sin(frame * 0.08 + i * 0.9) * 2.5
                else:
                    bar_pulse = 0.0

                pos_y = int(pos[1] + bar_pulse)
                canvas.paste(patch, (pos[0], pos_y), patch)
                top_centers[i] = np.array([tc[0], tc[1] + bar_pulse])

        # 4. Connecting Glowing Line & Infinite Traveling Light Orb
        if frame > 70:
            trend_alpha = int(230 * clamp((frame - 70) / 25.0))
            active_pts = [tc for tc in top_centers if tc is not None]
            if len(active_pts) >= 2:
                trend_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                tr_draw = ImageDraw.Draw(trend_layer)

                curve_pts = [tuple(p) for p in active_pts]
                tr_draw.line(curve_pts, fill=(0, 180, 255, trend_alpha), width=3)

                travel_cycle = 75.0
                t_travel = ((frame - 70) % travel_cycle) / travel_cycle
                seg_count = len(active_pts) - 1
                pos_f = t_travel * seg_count
                curr_idx = min(seg_count - 1, int(pos_f))
                sub_t = pos_f - curr_idx

                pA = active_pts[curr_idx]
                pB = active_pts[curr_idx + 1]
                pulse_pos = pA * (1.0 - sub_t) + pB * sub_t

                tr_draw.ellipse([pulse_pos[0]-18, pulse_pos[1]-18, pulse_pos[0]+18, pulse_pos[1]+18], fill=(0, 160, 255, int(trend_alpha * 0.35)))
                tr_draw.ellipse([pulse_pos[0]-11, pulse_pos[1]-11, pulse_pos[0]+11, pulse_pos[1]+11], fill=(120, 220, 255, int(trend_alpha * 0.75)))
                tr_draw.ellipse([pulse_pos[0]-6, pulse_pos[1]-6, pulse_pos[0]+6, pulse_pos[1]+6], fill=(255, 255, 255, trend_alpha))

                canvas.alpha_composite(trend_layer)

        # 5. Progressive Callouts & Pulsing Price Tickers
        callout_draw = ImageDraw.Draw(canvas)
        for i in range(7):
            tc = top_centers[i]
            if tc is None:
                continue

            line_start_f = 8 + i * 9 + 12
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

                num_pulse = math.sin(frame * 0.1 + i) * 1.5 if frame > line_start_f + LINE_DUR else 0.0
                txt_alpha = int(255 * text_t)
                callout_draw.text((pt_end[0], pt_elbow[1] - 52 + num_pulse), price_str, fill=(0, 108, 235, txt_alpha), font=font_price)

                c_color = color_down if data[i]["chg_type"] == "down" else (color_up if data[i]["chg_type"] == "up" else color_neu)
                c_color_a = (c_color[0], c_color[1], c_color[2], txt_alpha)
                callout_draw.text((pt_end[0] + 4, pt_elbow[1] + 8 + num_pulse), f"({data[i]['change']})", fill=c_color_a, font=font_change)

        # 6. High-Impact WEEK HIGH / LOW Badges
        if frame > 80:
            badge_alpha = int(255 * clamp((frame - 80) / 20.0))
            badge_float = math.sin((frame - 80) * 0.1) * 4.0

            badge_indices = [idx for idx in range(7) if data[idx]["badge"] is not None]
            for i in badge_indices:
                tc = top_centers[i]
                if tc is not None:
                    badge_txt = data[i]["badge"]
                    is_high = (badge_txt == "WEEK HIGH")

                    b_fill = (235, 135, 0, badge_alpha) if is_high else (215, 35, 35, badge_alpha)
                    b_border = (255, 210, 100, badge_alpha) if is_high else (255, 120, 120, badge_alpha)

                    card_w, card_h = 175, 42
                    bx = tc[0] - 165 if not is_high else tc[0] - 175
                    by = tc[1] - 175 + badge_float

                    callout_draw.rounded_rectangle([bx + 2, by + 4, bx + card_w + 2, by + card_h + 4], radius=8, fill=(0, 20, 40, int(badge_alpha * 0.35)))
                    callout_draw.rounded_rectangle([bx, by, bx + card_w, by + card_h], radius=8, fill=b_fill, outline=b_border, width=2)
                    callout_draw.text((bx + 14, by + 6), badge_txt, fill=(255, 255, 255, badge_alpha), font=font_badge)

        # FAST DIRECT-TO-PIPE STREAMING (Zero NumPy/OpenCV BGR conversion overhead)
        ffmpeg_proc.stdin.write(canvas.convert('RGB').tobytes())

        # Low-RAM Garbage Collection safeguard
        if frame % 60 == 0:
            gc.collect()

    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()
    return output_path

def main(duration_sec=None):
    return generate_perfect_fast_animation(duration_sec=duration_sec)

if __name__ == "__main__":
    main()
