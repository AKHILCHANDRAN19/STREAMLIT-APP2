import math
import os
import subprocess
import time
import glob
import random
import wave
import gc
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ==========================================
# CONFIGURATION & REPO ASSET PATHS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "Images")
FONTS_DIR = os.path.join(BASE_DIR, "Fonts")
AUDIOS_DIR = os.path.join(BASE_DIR, "Audios")
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")

os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(AUDIOS_DIR, exist_ok=True)

LOGO_PATH = os.path.join(IMAGES_DIR, "channel-logo.png")
LIKE_IMG_PATH = os.path.join(IMAGES_DIR, "Like.png")
SUB_IMG_PATH = os.path.join(IMAGES_DIR, "Subscribe.png")
WA_IMG_PATH = os.path.join(IMAGES_DIR, "Whatsapp.png")

OUTPUT_PATH = os.path.join(VIDEOS_DIR, "intro.mp4")
SFX_PATH = os.path.join(AUDIOS_DIR, "intro_sfx.wav")
FONT_MONT_EBOLD = os.path.join(FONTS_DIR, "Montserrat-ExtraBold.ttf")

WIDTH, HEIGHT = 1920, 1080
FPS = 30
DEFAULT_DURATION = 11.5


# ==========================================
# UTILITIES & EASING
# ==========================================
def log_step(step, total, msg):
    print(f"[{step}/{total}] {msg}", flush=True)

def get_font(path, size):
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

def ease_out_back(t, overshoot=1.55):
    t -= 1.0
    return t * t * ((overshoot + 1.0) * t + overshoot) + 1.0

def ease_in_cubic(t):
    return t * t * t


# ==========================================
# 1. AUDIO DETECTION & SFX SYNTHESIZER
# ==========================================
def get_random_prebuilt_audio_and_duration():
    """Finds user pre-built audio and reads its exact duration to prevent mid-sentence cut-offs."""
    valid_exts = (".wav", ".mp3", ".m4a", ".aac")
    audio_files = [
        f for f in glob.glob(os.path.join(AUDIOS_DIR, "*"))
        if f.lower().endswith(valid_exts)
        and not os.path.basename(f).startswith(("intro_sfx", "intro_master_mixed", "comp_", "price_", "master_"))
    ]
    if not audio_files:
        return None, DEFAULT_DURATION

    selected = random.choice(audio_files)
    duration = DEFAULT_DURATION

    try:
        if selected.lower().endswith(".wav"):
            with wave.open(selected, "rb") as wf:
                duration = wf.getnframes() / float(wf.getframerate())
        else:
            # Fallback probe via ffprobe if MP3/M4A
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", selected]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            duration = float(res.stdout.strip())
    except Exception as e:
        print(f"      [Audio Engine] Notice probing audio duration: {e}")

    # Ensure minimum 11.5s so all visual stages display completely
    final_duration = max(11.5, duration)
    return selected, final_duration


def synthesize_sfx_track(output_path, total_duration, sample_rate=44100):
    """Synthesizes the standalone SFX track for the exact length of the video."""
    total_samples = int(total_duration * sample_rate)
    left = np.zeros(total_samples, dtype=np.float32)
    right = np.zeros(total_samples, dtype=np.float32)

    def inject_sfx(start_sec, s_left, s_right):
        st_idx = int(start_sec * sample_rate)
        ed_idx = min(total_samples, st_idx + len(s_left))
        vl = ed_idx - st_idx
        if vl > 0:
            left[st_idx:ed_idx] += s_left[:vl]
            right[st_idx:ed_idx] += s_right[:vl]

    # --- SFX 1: Cinematic Sub-Bass Impact (t = 0.8s) ---
    t1 = np.linspace(0, 1.5, int(sample_rate * 1.5), endpoint=False)
    freq_sweep = 135.0 * np.exp(-t1 * 3.2) + 38.0
    phase = 2.0 * np.pi * np.cumsum(freq_sweep) / sample_rate
    sub = np.sin(phase) * np.exp(-t1 * 2.1)
    punch = np.random.uniform(-1.0, 1.0, len(t1)) * np.exp(-t1 * 40.0)
    resonance = np.sin(2.0 * np.pi * 510.0 * t1) * np.exp(-t1 * 5.0) * 0.2
    impact = (sub * 0.75 + punch * 0.35 + resonance) * 0.95
    inject_sfx(0.8, impact, impact)

    # --- SFX 2: Pop & Chime for Like & Subscribe (t = 4.5s) ---
    t2 = np.linspace(0, 1.2, int(sample_rate * 1.2), endpoint=False)
    whoosh_freq = 240.0 + 850.0 * (t2 / 0.25) * (t2 < 0.25)
    whoosh = np.sin(2.0 * np.pi * np.cumsum(whoosh_freq) / sample_rate) * np.exp(-t2 * 6.0) * (t2 < 0.25) * 0.3
    bell = (np.sin(2.0 * np.pi * 880.0 * t2) * 0.5 + np.sin(2.0 * np.pi * 1320.0 * t2) * 0.35) * np.exp(-t2 * 3.8)
    pop = np.sin(2.0 * np.pi * 330.0 * t2) * np.exp(-t2 * 25.0) * 0.35
    inject_sfx(4.5, (bell * 0.6 + pop * 0.3 + whoosh * 0.2) * 0.85, (bell * 0.7 + pop * 0.3 + whoosh * 0.2) * 0.95)

    # --- SFX 3: WhatsApp Notification Glass Ping (t = 8.0s) ---
    t3 = np.linspace(0, 1.3, int(sample_rate * 1.3), endpoint=False)
    ping = (np.sin(2.0 * np.pi * 1046.5 * t3) * 0.5 + np.sin(2.0 * np.pi * 2093.0 * t3) * 0.3) * np.exp(-t3 * 3.2)
    glass_tap = np.sin(2.0 * np.pi * 420.0 * t3) * np.exp(-t3 * 30.0) * 0.25
    inject_sfx(8.0, (ping * 0.8 + glass_tap) * 0.85, (ping * 0.75 + glass_tap) * 0.80)

    left = np.tanh(left) * 0.92
    right = np.tanh(right) * 0.92

    left_int16 = (left * 32767).astype(np.int16)
    right_int16 = (right * 32767).astype(np.int16)

    interleaved = np.empty((left_int16.size + right_int16.size,), dtype=np.int16)
    interleaved[0::2] = left_int16
    interleaved[1::2] = right_int16

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(interleaved.tobytes())

    return output_path


# ==========================================
# 2. BACKGROUND & TEXT RENDERING
# ==========================================
def create_cinematic_dark_blue_bg(w, h):
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2.0, h / 2.0
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    max_d = np.sqrt(cx**2 + cy**2)
    norm = np.clip(dist / max_d, 0.0, 1.0)

    b = np.clip(95 * (1.0 - norm**1.3) + 12, 8, 255).astype(np.uint8)
    g = np.clip(32 * (1.0 - norm**1.6) + 3, 2, 255).astype(np.uint8)
    r = np.clip(10 * (1.0 - norm**1.9) + 1, 0, 255).astype(np.uint8)

    bg = np.dstack((b, g, r))
    return cv2.GaussianBlur(bg, (45, 45), 0)


def render_gold_text_layer():
    text = "KERALA GOLD DESK"
    font_size = 180
    font = get_font(FONT_MONT_EBOLD, font_size)
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    while True:
        bbox = dummy_draw.textbbox((0, 0), text, font=font)
        t_w = bbox[2] - bbox[0]
        if t_w <= 1750 or font_size <= 60:
            break
        font_size -= 5
        font = get_font(FONT_MONT_EBOLD, font_size)

    t_h = bbox[3] - bbox[1]
    pad_x, pad_y = 120, 100
    layer_w, layer_h = int(t_w + pad_x * 2), int(t_h + pad_y * 2)
    cx, cy = layer_w // 2, layer_h // 2 - 15

    gold_grad = np.zeros((layer_h, layer_w, 4), dtype=np.uint8)
    for y in range(layer_h):
        t = y / max(1, layer_h - 1)
        if t < 0.25:
            k = t / 0.25
            r, g, b = int(255*(1-k) + 255*k), int(252*(1-k) + 215*k), int(220*(1-k) + 18*k)
        elif t < 0.65:
            k = (t - 0.25) / 0.40
            r, g, b = int(255*(1-k) + 215*k), int(215*(1-k) + 145*k), int(18*(1-k) + 6*k)
        else:
            k = (t - 0.65) / 0.35
            r, g, b = int(215*(1-k) + 110*k), int(145*(1-k) + 65*k), int(6*(1-k) + 2*k)
        gold_grad[y, :, 0] = b
        gold_grad[y, :, 1] = g
        gold_grad[y, :, 2] = r
        gold_grad[y, :, 3] = 255

    mask_img = Image.new("L", (layer_w, layer_h), 0)
    ImageDraw.Draw(mask_img).text((cx, cy), text, fill=255, font=font, anchor="mm")
    gold_grad[:, :, 3] = np.array(mask_img)

    stroke_img = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    ImageDraw.Draw(stroke_img).text((cx, cy), text, fill=(0,0,0,0), font=font, anchor="mm", stroke_width=12, stroke_fill=(6,3,1,255))
    stroke_bgra = cv2.cvtColor(np.array(stroke_img), cv2.COLOR_RGBA2BGRA)

    shadow_img = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    for off in range(32, 0, -2):
        shadow_draw.text((cx + off, cy + off), text, fill=(2,2,6,170), font=font, anchor="mm", stroke_width=8, stroke_fill=(2,2,6,170))
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(10))
    shadow_bgra = cv2.cvtColor(np.array(shadow_img), cv2.COLOR_RGBA2BGRA)

    master = np.zeros((layer_h, layer_w, 4), dtype=np.uint8)
    alpha_s = shadow_bgra[:, :, 3] / 255.0
    for c in range(3): master[:, :, c] = (shadow_bgra[:, :, c] * alpha_s).astype(np.uint8)
    master[:, :, 3] = shadow_bgra[:, :, 3]

    alpha_str = stroke_bgra[:, :, 3] / 255.0
    for c in range(3): master[:, :, c] = (master[:, :, c] * (1 - alpha_str) + stroke_bgra[:, :, c] * alpha_str).astype(np.uint8)
    master[:, :, 3] = np.maximum(master[:, :, 3], stroke_bgra[:, :, 3])

    alpha_g = gold_grad[:, :, 3] / 255.0
    for c in range(3): master[:, :, c] = (master[:, :, c] * (1 - alpha_g) + gold_grad[:, :, c] * alpha_g).astype(np.uint8)
    master[:, :, 3] = np.maximum(master[:, :, 3], gold_grad[:, :, 3])

    return master


# ==========================================
# 3. UI ASSET BUILDERS & COMPOSITING
# ==========================================
def load_png_asset(path, target_width=None, target_height=None):
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA")
        if target_width and target_height:
            img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        elif target_width:
            ratio = target_width / float(img.width)
            h = int(img.height * ratio)
            img = img.resize((target_width, h), Image.Resampling.LANCZOS)
        elif target_height:
            ratio = target_height / float(img.height)
            w = int(img.width * ratio)
            img = img.resize((w, target_height), Image.Resampling.LANCZOS)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGRA)
    return None

def add_drop_shadow(raw_bgra, blur=35, opacity=0.75):
    if raw_bgra is None: return None
    h, w = raw_bgra.shape[:2]
    pad = 100
    shadow = np.zeros((h + pad, w + pad, 4), dtype=np.uint8)
    shadow[pad//2 : pad//2 + h, pad//2 : pad//2 + w, 3] = (raw_bgra[:, :, 3] * opacity).astype(np.uint8)
    shadow = cv2.GaussianBlur(shadow, (blur, blur), 0)
    return overlay_direct(shadow, raw_bgra, pad//2, pad//2 - 10)

def prepare_like_icon():
    raw = load_png_asset(LIKE_IMG_PATH, target_height=350)
    return add_drop_shadow(raw)

def prepare_subscribe_button():
    raw = load_png_asset(SUB_IMG_PATH, target_height=180)
    if raw is None:
        badge = Image.new("RGBA", (600, 180), (0, 0, 0, 0))
        ImageDraw.Draw(badge).rounded_rectangle([0, 0, 600, 180], radius=90, fill=(220, 20, 20, 255))
        raw = cv2.cvtColor(np.array(badge), cv2.COLOR_RGBA2BGRA)
    return add_drop_shadow(raw)

def create_whatsapp_banner():
    card_w, card_h = 1000, 160
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    draw.rounded_rectangle([0, 0, card_w, card_h], radius=80, fill=(6, 26, 16, 245), outline=(37, 211, 102, 240), width=5)
    font_wa = get_font(FONT_MONT_EBOLD, 46)
    draw.text((550, 80), "JOIN WHATSAPP CHANNEL", fill=(255, 255, 255, 255), font=font_wa, anchor="mm")
    card_bgra = cv2.cvtColor(np.array(card), cv2.COLOR_RGBA2BGRA)

    wa_icon = load_png_asset(WA_IMG_PATH, target_width=130, target_height=130)
    if wa_icon is not None:
        card_bgra = overlay_direct(card_bgra, wa_icon, 40, 15)

    return add_drop_shadow(card_bgra)

def overlay_direct(dest, src, x, y):
    h, w = src.shape[:2]
    dh, dw = dest.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(dw, x + w), min(dh, y + h)
    ox1, oy1 = x1 - x, y1 - y
    ox2, oy2 = ox1 + (x2 - x1), oy1 + (y2 - y1)

    if x1 >= x2 or y1 >= y2:
        return dest

    sub_src = src[oy1:oy2, ox1:ox2]
    alpha = sub_src[:, :, 3] / 255.0
    alpha_3d = np.dstack([alpha, alpha, alpha])
    dest[y1:y2, x1:x2, :3] = (dest[y1:y2, x1:x2, :3] * (1.0 - alpha_3d) + sub_src[:, :, :3] * alpha_3d).astype(np.uint8)
    dest[y1:y2, x1:x2, 3] = np.maximum(dest[y1:y2, x1:x2, 3], sub_src[:, :, 3])
    return dest

def overlay_bgra(bg, overlay, x, y):
    h, w = overlay.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(WIDTH, x + w), min(HEIGHT, y + h)
    ox1, oy1 = x1 - x, y1 - y
    ox2, oy2 = ox1 + (x2 - x1), oy1 + (y2 - y1)

    if x1 >= x2 or y1 >= y2:
        return

    sub = overlay[oy1:oy2, ox1:ox2]
    alpha = sub[:, :, 3] / 255.0
    alpha_3d = np.dstack([alpha, alpha, alpha])
    bg[y1:y2, x1:x2] = (bg[y1:y2, x1:x2] * (1.0 - alpha_3d) + sub[:, :, :3] * alpha_3d).astype(np.uint8)


# ==========================================
# 4. MASTER COMPOSITING PIPELINE
# ==========================================
def main():
    log_step(1, 6, "Probing pre-built audio duration...")
    prebuilt_audio, audio_duration = get_random_prebuilt_audio_and_duration()
    TOTAL_DURATION = audio_duration
    TOTAL_FRAMES = int(FPS * TOTAL_DURATION)
    log_step(1, 6, f"Matched Video Duration to Audio: {TOTAL_DURATION:.2f}s ({TOTAL_FRAMES} frames)")

    synthesize_sfx_track(SFX_PATH, total_duration=TOTAL_DURATION)

    bg_base = create_cinematic_dark_blue_bg(WIDTH, HEIGHT)
    log_step(2, 6, "Loading channel logo with 3D drop shadows...")
    logo_size = 350
    logo_raw = load_png_asset(LOGO_PATH, target_width=logo_size, target_height=logo_size)
    if logo_raw is None:
        logo_raw = np.zeros((logo_size, logo_size, 4), dtype=np.uint8)
        cv2.circle(logo_raw, (logo_size//2, logo_size//2), 160, (20, 175, 220, 255), -1)
        cv2.putText(logo_raw, "KGD", (80, 210), cv2.FONT_HERSHEY_DUPLEX, 3.5, (255, 255, 255, 255), 6)

    logo_base = add_drop_shadow(logo_raw, blur=41, opacity=0.8)

    log_step(3, 6, "Extracting original pixel disintegration cloud from gold typography...")
    gold_text_layer = render_gold_text_layer()

    alpha = gold_text_layer[:, :, 3]
    y_idx, x_idx = np.where(alpha > 35)
    total_px = len(x_idx)
    colors = gold_text_layer[y_idx, x_idx, :3]

    title_x = WIDTH // 2 - gold_text_layer.shape[1] // 2
    title_y = 150
    logo_center_y = 620

    p_x = (x_idx + title_x).astype(np.float32)
    p_y = (y_idx + title_y).astype(np.float32)

    np.random.seed(42)
    vx = np.random.uniform(-7.0, 7.0, total_px).astype(np.float32)
    vy = np.random.uniform(-5.5, 2.0, total_px).astype(np.float32)
    gravity = np.random.uniform(0.95, 1.65, total_px).astype(np.float32)

    log_step(4, 6, "Compositing UI cards...")
    like_overlay = prepare_like_icon()
    sub_overlay = prepare_subscribe_button()
    wa_overlay = create_whatsapp_banner()

    log_step(5, 6, "Streaming to FFmpeg encoder...")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "bgr24", "-r", str(FPS), "-i", "-"
    ]

    if prebuilt_audio and os.path.exists(prebuilt_audio):
        log_step(5, 6, f"Layering SFX onto: {os.path.basename(prebuilt_audio)}")
        ffmpeg_cmd.extend([
            "-i", prebuilt_audio,
            "-i", SFX_PATH,
            "-filter_complex",
            "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0,apad[a_bg];"
            "[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.85[a_sfx];"
            "[a_bg][a_sfx]amix=inputs=2:duration=longest:dropout_transition=0,volume=1.6[aout]",
            "-map", "0:v", "-map", "[aout]"
        ])
    else:
        ffmpeg_cmd.extend([
            "-i", SFX_PATH,
            "-map", "0:v", "-map", "1:a"
        ])

    ffmpeg_cmd.extend([
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-b:v", "1800k", "-maxrate", "2200k", "-bufsize", "4000k",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-t", str(TOTAL_DURATION),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUTPUT_PATH
    ])

    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    start_time = time.time()

    np.random.seed(99)
    env_particles = 1500
    sp_x = np.random.uniform(-100, WIDTH + 100, env_particles)
    sp_y = np.random.uniform(-100, HEIGHT + 100, env_particles)
    sp_vx = np.random.uniform(-1.5, 1.5, env_particles)
    sp_vy = np.random.uniform(0.5, 3.5, env_particles)

    gold_shades = [(60, 210, 245), (30, 180, 255), (10, 140, 220)]
    sp_color_idx = np.random.randint(0, 3, env_particles)
    sp_sizes = np.random.randint(2, 5, env_particles)

    # ==================================================
    # MASTER RENDER LOOP (Full Duration)
    # ==================================================
    for frame_idx in range(TOTAL_FRAMES):
        t = frame_idx / FPS
        frame = bg_base.copy()

        # Update Background Particles
        sp_x += sp_vx
        sp_y += sp_vy

        # Shockwave upon text drop (t = 0.8s)
        if 0.8 <= t <= 2.2:
            dx = sp_x - WIDTH // 2
            dy = sp_y - HEIGHT // 2
            dist = np.sqrt(dx**2 + dy**2) + 0.1
            shock_mask = dist < 850
            if np.any(shock_mask):
                force = (1.0 - dist[shock_mask] / 850.0) * 35.0
                sp_vx[shock_mask] += (dx[shock_mask] / dist[shock_mask]) * force
                sp_vy[shock_mask] += (dy[shock_mask] / dist[shock_mask]) * force

        sp_vx *= 0.88
        sp_vy = sp_vy * 0.88 + 0.12 * 2.0
        sp_x = sp_x % WIDTH
        sp_y = sp_y % HEIGHT

        draw_x, draw_y = sp_x.astype(np.int32), sp_y.astype(np.int32)
        for i in range(env_particles):
            cv2.circle(frame, (draw_x[i], draw_y[i]), sp_sizes[i], gold_shades[sp_color_idx[i]], -1)

        # --------------------------------------------------
        # STAGE 1: CHANNEL NAME & LOGO (0.0s – 4.5s)
        # --------------------------------------------------
        if t < 3.8:
            drop_dur = 0.85
            if t < drop_dur:
                prog = t / drop_dur
                scale = 4.2 - 3.2 * ease_out_back(prog, overshoot=1.5)
                alpha_f = min(1.0, prog * 1.8)
            else:
                scale = 1.0
                alpha_f = 1.0

            tw = max(10, int(gold_text_layer.shape[1] * scale))
            th = max(10, int(gold_text_layer.shape[0] * scale))
            cur_text = cv2.resize(gold_text_layer, (tw, th), interpolation=cv2.INTER_LINEAR)
            if alpha_f < 1.0:
                cur_text[:, :, 3] = (cur_text[:, :, 3] * alpha_f).astype(np.uint8)
            overlay_bgra(frame, cur_text, WIDTH//2 - tw//2, int(title_y + gold_text_layer.shape[0]//2 - th//2))

            lw = max(10, int(logo_base.shape[1] * scale))
            lh = max(10, int(logo_base.shape[0] * scale))
            cur_logo = cv2.resize(logo_base, (lw, lh), interpolation=cv2.INTER_LINEAR)
            if alpha_f < 1.0:
                cur_logo[:, :, 3] = (cur_logo[:, :, 3] * alpha_f).astype(np.uint8)

            if t >= drop_dur:
                pulse = 1.0 + 0.02 * math.sin((t - drop_dur) * 6.0)
                plw, plh = int(logo_base.shape[1] * pulse), int(logo_base.shape[0] * pulse)
                cur_logo = cv2.resize(logo_base, (plw, plh), interpolation=cv2.INTER_LINEAR)
                lx, ly = WIDTH//2 - plw//2, logo_center_y - plh//2
            else:
                lx, ly = WIDTH//2 - lw//2, logo_center_y - lh//2

            overlay_bgra(frame, cur_logo, lx, ly)

            if 0.75 <= t <= 1.4:
                sw_p = (t - 0.75) / 0.65
                cv2.circle(frame, (WIDTH//2, logo_center_y - 80), int(150 + sw_p * 850), (40, 195, 235), max(1, int(18 * (1.0 - sw_p))))

        # 1x1 Pixel Disintegration (3.8s to 4.5s -> clears completely at 4.5s)
        elif 3.8 <= t < 4.5:
            dt = t - 3.8
            l_fade = max(0.0, 1.0 - dt * 2.2)
            if l_fade > 0:
                cw, ch = max(2, int(logo_base.shape[1] * l_fade)), max(2, int(logo_base.shape[0] * l_fade))
                f_logo = cv2.resize(logo_base, (cw, ch), interpolation=cv2.INTER_LINEAR)
                f_logo[:, :, 3] = (f_logo[:, :, 3] * l_fade).astype(np.uint8)
                overlay_bgra(frame, f_logo, WIDTH//2 - cw//2, logo_center_y - ch//2)

            cur_px = p_x + vx * (dt * 32.0)
            cur_py = p_y + vy * (dt * 32.0) + 0.5 * gravity * ((dt * 32.0) ** 2)
            valid = (cur_px >= 0) & (cur_px < WIDTH) & (cur_py >= 0) & (cur_py < HEIGHT)
            idx_v = np.where(valid)[0]
            frame[cur_py[idx_v].astype(np.int32), cur_px[idx_v].astype(np.int32)] = colors[idx_v]

        # --------------------------------------------------
        # STAGE 2: LIKE & SUBSCRIBE (4.5s – 8.0s -> Exactly 3.5s)
        # --------------------------------------------------
        elif 4.5 <= t < 8.0:
            t_stage = t - 4.5
            if t_stage < 0.6:
                scale_ui = ease_out_back(t_stage / 0.6, overshoot=1.3)
            elif t_stage < 3.0:
                scale_ui = 1.0 + 0.02 * math.sin((t_stage - 0.6) * 8.0)
            else:
                scale_ui = max(0.0, 1.0 - ease_in_cubic((t_stage - 3.0) / 0.5))

            if scale_ui > 0.05:
                w_like = int(like_overlay.shape[1] * scale_ui)
                h_like = int(like_overlay.shape[0] * scale_ui)
                w_sub = int(sub_overlay.shape[1] * scale_ui)
                h_sub = int(sub_overlay.shape[0] * scale_ui)

                gap = int(120 * scale_ui)
                total_w = w_like + gap + w_sub
                start_x = WIDTH // 2 - total_w // 2
                cy = HEIGHT // 2

                like_x, like_y = start_x, cy - h_like // 2
                sub_x, sub_y = start_x + w_like + gap, cy - h_sub // 2

                overlay_bgra(frame, cv2.resize(like_overlay, (w_like, h_like)), like_x, like_y)
                overlay_bgra(frame, cv2.resize(sub_overlay, (w_sub, h_sub)), sub_x, sub_y)

        # --------------------------------------------------
        # STAGE 3: WHATSAPP BANNER (8.0s – End of Full Audio Duration)
        # --------------------------------------------------
        elif t >= 8.0:
            t_stage = t - 8.0
            prog = min(1.0, t_stage / 0.6)
            scale_wa = ease_out_back(prog, overshoot=1.3)

            # Stays on screen with subtle breathing until the entire audio sentence finishes
            if t_stage > 0.6:
                scale_wa *= (1.0 + 0.015 * math.sin((t_stage - 0.6) * 6.0))

            ww, wh = int(wa_overlay.shape[1] * scale_wa), int(wa_overlay.shape[0] * scale_wa)
            if ww > 4:
                overlay_bgra(frame, cv2.resize(wa_overlay, (ww, wh)), WIDTH//2 - ww//2, HEIGHT//2 - wh//2)

        process.stdin.write(frame.tobytes())

        if frame_idx % 60 == 0:
            gc.collect()

        if frame_idx % 15 == 0 or frame_idx == TOTAL_FRAMES - 1:
            print(f"      [Matrix Engine] Frame {frame_idx + 1:03d}/{TOTAL_FRAMES} | Speed: {(frame_idx + 1) / max(0.001, (time.time() - start_time)):4.1f} FPS", end="\r", flush=True)

    print()
    process.stdin.close()
    process.wait()
    log_step(6, 6, f"Pipeline Complete! Video mapped to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
