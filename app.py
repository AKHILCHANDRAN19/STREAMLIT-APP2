import os
import glob
import math
import time
import wave
import subprocess
import gc
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ==========================================
# 1. HELPER ROUTINES & EASING
# ==========================================
def ease_out_back(t, overshoot=1.55):
    t -= 1.0
    return t * t * ((overshoot + 1.0) * t + overshoot) + 1.0

def ease_in_cubic(t):
    return t * t * t

def get_font(path, size):
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

def load_png_asset(path, target_width=None, target_height=None):
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA")
        if target_width and target_height:
            img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        elif target_width:
            ratio = target_width / float(img.width)
            img = img.resize((target_width, int(img.height * ratio)), Image.Resampling.LANCZOS)
        elif target_height:
            ratio = target_height / float(img.height)
            img = img.resize((int(img.width * ratio), target_height), Image.Resampling.LANCZOS)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGRA)
    return None

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

def overlay_bgra(bg, overlay, x, y, width=1920, height=1080):
    h, w = overlay.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(width, x + w), min(height, y + h)
    ox1, oy1 = x1 - x, y1 - y
    ox2, oy2 = ox1 + (x2 - x1), oy1 + (y2 - y1)

    if x1 >= x2 or y1 >= y2:
        return

    sub = overlay[oy1:oy2, ox1:ox2]
    alpha = sub[:, :, 3] / 255.0
    alpha_3d = np.dstack([alpha, alpha, alpha])
    bg[y1:y2, x1:x2] = (bg[y1:y2, x1:x2] * (1.0 - alpha_3d) + sub[:, :, :3] * alpha_3d).astype(np.uint8)

def add_drop_shadow(raw_bgra, blur=35, opacity=0.75):
    if raw_bgra is None:
        return None
    h, w = raw_bgra.shape[:2]
    pad = 100
    shadow = np.zeros((h + pad, w + pad, 4), dtype=np.uint8)
    shadow[pad//2 : pad//2 + h, pad//2 : pad//2 + w, 3] = (raw_bgra[:, :, 3] * opacity).astype(np.uint8)
    shadow = cv2.GaussianBlur(shadow, (blur, blur), 0)
    return overlay_direct(shadow, raw_bgra, pad//2, pad//2 - 10)


# ==========================================
# 2. GRAPHIC ASSET GENERATORS
# ==========================================
def create_cinematic_dark_blue_bg(w=1920, h=1080):
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2.0, h / 2.0
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    norm = np.clip(dist / np.sqrt(cx**2 + cy**2), 0.0, 1.0)

    b = np.clip(95 * (1.0 - norm**1.3) + 12, 8, 255).astype(np.uint8)
    g = np.clip(32 * (1.0 - norm**1.6) + 3, 2, 255).astype(np.uint8)
    r = np.clip(10 * (1.0 - norm**1.9) + 1, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(np.dstack((b, g, r)), (45, 45), 0)

def render_gold_text_layer(font_path):
    text = "KERALA GOLD DESK"
    font_size = 180
    font = get_font(font_path, font_size)
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    while True:
        bbox = dummy_draw.textbbox((0, 0), text, font=font)
        t_w = bbox[2] - bbox[0]
        if t_w <= 1750 or font_size <= 60:
            break
        font_size -= 5
        font = get_font(font_path, font_size)

    t_h = bbox[3] - bbox[1]
    layer_w, layer_h = int(t_w + 240), int(t_h + 200)
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
        gold_grad[y, :, 0], gold_grad[y, :, 1], gold_grad[y, :, 2], gold_grad[y, :, 3] = b, g, r, 255

    mask_img = Image.new("L", (layer_w, layer_h), 0)
    ImageDraw.Draw(mask_img).text((cx, cy), text, fill=255, font=font, anchor="mm")
    gold_grad[:, :, 3] = np.array(mask_img)

    stroke_img = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    ImageDraw.Draw(stroke_img).text((cx, cy), text, fill=(0,0,0,0), font=font, anchor="mm", stroke_width=12, stroke_fill=(6,3,1,255))
    stroke_bgra = cv2.cvtColor(np.array(stroke_img), cv2.COLOR_RGBA2BGRA)

    shadow_img = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_img)
    for off in range(32, 0, -2):
        s_draw.text((cx + off, cy + off), text, fill=(2,2,6,170), font=font, anchor="mm", stroke_width=8, stroke_fill=(2,2,6,170))
    shadow_bgra = cv2.cvtColor(np.array(shadow_img.filter(ImageFilter.GaussianBlur(10))), cv2.COLOR_RGBA2BGRA)

    master = np.zeros((layer_h, layer_w, 4), dtype=np.uint8)
    alpha_s = shadow_bgra[:, :, 3] / 255.0
    for c in range(3):
        master[:, :, c] = (shadow_bgra[:, :, c] * alpha_s).astype(np.uint8)
    master[:, :, 3] = shadow_bgra[:, :, 3]

    alpha_str = stroke_bgra[:, :, 3] / 255.0
    for c in range(3):
        master[:, :, c] = (master[:, :, c] * (1 - alpha_str) + stroke_bgra[:, :, c] * alpha_str).astype(np.uint8)
    master[:, :, 3] = np.maximum(master[:, :, 3], stroke_bgra[:, :, 3])

    alpha_g = gold_grad[:, :, 3] / 255.0
    for c in range(3):
        master[:, :, c] = (master[:, :, c] * (1 - alpha_g) + gold_grad[:, :, c] * alpha_g).astype(np.uint8)
    master[:, :, 3] = np.maximum(master[:, :, 3], gold_grad[:, :, 3])

    return master

def prepare_subscribe_button(sub_path):
    raw = load_png_asset(sub_path, target_height=180)
    if raw is None:
        badge = Image.new("RGBA", (600, 180), (0, 0, 0, 0))
        ImageDraw.Draw(badge).rounded_rectangle([0, 0, 600, 180], radius=90, fill=(220, 20, 20, 255))
        raw = cv2.cvtColor(np.array(badge), cv2.COLOR_RGBA2BGRA)
    return add_drop_shadow(raw)

def create_whatsapp_banner(wa_path, font_path):
    card_w, card_h = 1000, 160
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([0, 0, card_w, card_h], radius=80, fill=(6, 26, 16, 245), outline=(37, 211, 102, 240), width=5)
    font_wa = get_font(font_path, 46)
    draw.text((550, 80), "JOIN WHATSAPP CHANNEL", fill=(255, 255, 255, 255), font=font_wa, anchor="mm")
    card_bgra = cv2.cvtColor(np.array(card), cv2.COLOR_RGBA2BGRA)

    wa_icon = load_png_asset(wa_path, target_width=130, target_height=130)
    if wa_icon is not None:
        card_bgra = overlay_direct(card_bgra, wa_icon, 40, 15)
    return add_drop_shadow(card_bgra)


# ==========================================
# 3. DIRECT INTRO BUILDER FOR APP.PY
# ==========================================
def generate_intro(output_path="Videos/intro.mp4", base_dir=None):
    """
    Directly renders the intro video with synchronized audio.
    Outputs strict specs: 1920x1080, 30fps, YUV420P, AAC 48000Hz stereo.
    Guarantees no missing audio tracks to prevent downstream merge corruption.
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    images_dir = os.path.join(base_dir, "Images")
    fonts_dir = os.path.join(base_dir, "Fonts")
    audios_dir = os.path.join(base_dir, "Audios")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logo_path = os.path.join(images_dir, "channel-logo.png")
    like_path = os.path.join(images_dir, "Like.png")
    sub_path = os.path.join(images_dir, "Subscribe.png")
    wa_path = os.path.join(images_dir, "Whatsapp.png")
    font_mont = os.path.join(fonts_dir, "Montserrat-ExtraBold.ttf")

    # Audio resolution
    audio_files = glob.glob(os.path.join(audios_dir, "*.wav"))
    selected_audio = None
    duration_sec = 10.0

    if audio_files:
        import random
        selected_audio = random.choice(audio_files)
        try:
            with wave.open(selected_audio, 'r') as w:
                duration_sec = w.getnframes() / float(w.getframerate())
        except Exception:
            selected_audio = None

    width, height, fps = 1920, 1080, 30
    total_frames = int(fps * duration_sec)

    bg_base = create_cinematic_dark_blue_bg(width, height)
    logo_raw = load_png_asset(logo_path, target_width=350, target_height=350)
    if logo_raw is None:
        logo_raw = np.zeros((350, 350, 4), dtype=np.uint8)
        cv2.circle(logo_raw, (175, 175), 160, (20, 175, 220, 255), -1)
        cv2.putText(logo_raw, "KGD", (80, 210), cv2.FONT_HERSHEY_DUPLEX, 3.5, (255, 255, 255, 255), 6)

    logo_base = add_drop_shadow(logo_raw, blur=41, opacity=0.8)
    gold_text_layer = render_gold_text_layer(font_mont)

    alpha = gold_text_layer[:, :, 3]
    y_idx, x_idx = np.where(alpha > 35)
    total_px = len(x_idx)
    colors = gold_text_layer[y_idx, x_idx, :3]

    title_x = width // 2 - gold_text_layer.shape[1] // 2
    title_y = 150
    logo_center_y = 620

    p_x = (x_idx + title_x).astype(np.float32)
    p_y = (y_idx + title_y).astype(np.float32)

    np.random.seed(42)
    vx = np.random.uniform(-7.0, 7.0, total_px).astype(np.float32)
    vy = np.random.uniform(-5.5, 2.0, total_px).astype(np.float32)
    gravity = np.random.uniform(0.95, 1.65, total_px).astype(np.float32)

    like_overlay = add_drop_shadow(load_png_asset(like_path, target_height=350))
    sub_overlay = prepare_subscribe_button(sub_path)
    wa_overlay = create_whatsapp_banner(wa_path, font_mont)

    # Bulletproof FFmpeg Pipeline: Always forces 48000Hz stereo AAC
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24", "-r", str(fps), "-i", "-"
    ]

    if selected_audio:
        ffmpeg_cmd.extend(["-i", selected_audio])
    else:
        # Generate dummy silence if audio is missing so streams match downstream
        ffmpeg_cmd.extend(["-f", "lavfi", "-t", str(duration_sec), "-i", "anullsrc=r=48000:cl=stereo"])

    ffmpeg_cmd.extend([
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-threads", "2",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-pix_fmt", "yuv420p", "-shortest", output_path
    ])

    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # Ambient particles
    np.random.seed(99)
    env_particles = 1500
    sp_x = np.random.uniform(-100, width + 100, env_particles)
    sp_y = np.random.uniform(-100, height + 100, env_particles)
    sp_vx = np.random.uniform(-1.5, 1.5, env_particles)
    sp_vy = np.random.uniform(0.5, 3.5, env_particles)
    gold_shades = [(60, 210, 245), (30, 180, 255), (10, 140, 220)]
    sp_color_idx = np.random.randint(0, 3, env_particles)
    sp_sizes = np.random.randint(2, 5, env_particles)

    for frame_idx in range(total_frames):
        t_real = frame_idx / fps
        t_norm = t_real * (10.0 / duration_sec)
        frame = bg_base.copy()

        sp_x += sp_vx
        sp_y += sp_vy

        if 0.8 <= t_norm <= 2.2:
            dx = sp_x - width // 2
            dy = sp_y - height // 2
            dist = np.sqrt(dx**2 + dy**2) + 0.1
            shock_mask = dist < 850
            if np.any(shock_mask):
                force = (1.0 - dist[shock_mask] / 850.0) * 35.0
                sp_vx[shock_mask] += (dx[shock_mask] / dist[shock_mask]) * force
                sp_vy[shock_mask] += (dy[shock_mask] / dist[shock_mask]) * force

        sp_vx *= 0.88
        sp_vy = sp_vy * 0.88 + 0.12 * 2.0
        sp_x %= width
        sp_y %= height

        draw_x, draw_y = sp_x.astype(np.int32), sp_y.astype(np.int32)
        for i in range(env_particles):
            cv2.circle(frame, (draw_x[i], draw_y[i]), sp_sizes[i], gold_shades[sp_color_idx[i]], -1)

        # Stage 1: Impact (0.0 - 2.5)
        if t_norm < 2.5:
            drop_dur = 0.85
            prog = min(1.0, t_norm / drop_dur)
            scale = (4.2 - 3.2 * ease_out_back(prog, 1.5)) if t_norm < drop_dur else 1.0
            alpha_f = min(1.0, prog * 1.8)

            tw, th = max(10, int(gold_text_layer.shape[1] * scale)), max(10, int(gold_text_layer.shape[0] * scale))
            cur_text = cv2.resize(gold_text_layer, (tw, th), interpolation=cv2.INTER_LINEAR)
            if alpha_f < 1.0:
                cur_text[:, :, 3] = (cur_text[:, :, 3] * alpha_f).astype(np.uint8)
            overlay_bgra(frame, cur_text, width//2 - tw//2, int(title_y + gold_text_layer.shape[0]//2 - th//2))

            lw, lh = max(10, int(logo_base.shape[1] * scale)), max(10, int(logo_base.shape[0] * scale))
            cur_logo = cv2.resize(logo_base, (lw, lh), interpolation=cv2.INTER_LINEAR)
            if alpha_f < 1.0:
                cur_logo[:, :, 3] = (cur_logo[:, :, 3] * alpha_f).astype(np.uint8)

            if t_norm >= drop_dur:
                pulse = 1.0 + 0.02 * math.sin((t_norm - drop_dur) * 6.0)
                cur_logo = cv2.resize(logo_base, (int(logo_base.shape[1] * pulse), int(logo_base.shape[0] * pulse)))
            overlay_bgra(frame, cur_logo, width//2 - cur_logo.shape[1]//2, logo_center_y - cur_logo.shape[0]//2)

            if 0.75 <= t_norm <= 1.4:
                sw_p = (t_norm - 0.75) / 0.65
                cv2.circle(frame, (width//2, logo_center_y - 80), int(150 + sw_p * 850), (40, 195, 235), max(1, int(18 * (1.0 - sw_p))))

        # Stage 2: Disintegration (2.5 - 5.0)
        elif 2.5 <= t_norm < 5.0:
            dt = t_norm - 2.5
            l_fade = max(0.0, 1.0 - dt * 2.0)
            if l_fade > 0:
                f_logo = cv2.resize(logo_base, (max(2, int(logo_base.shape[1]*l_fade)), max(2, int(logo_base.shape[0]*l_fade))))
                f_logo[:, :, 3] = (f_logo[:, :, 3] * l_fade).astype(np.uint8)
                overlay_bgra(frame, f_logo, width//2 - f_logo.shape[1]//2, logo_center_y - f_logo.shape[0]//2)

            cur_px = p_x + vx * (dt * 32.0)
            cur_py = p_y + vy * (dt * 32.0) + 0.5 * gravity * ((dt * 32.0) ** 2)
            valid = (cur_px >= 0) & (cur_px < width) & (cur_py >= 0) & (cur_py < height)
            idx_v = np.where(valid)[0]
            frame[cur_py[idx_v].astype(np.int32), cur_px[idx_v].astype(np.int32)] = colors[idx_v]

        # Stage 3: Like & Subscribe (5.0 - 7.5)
        elif 5.0 <= t_norm < 7.5:
            if t_norm < 5.6:
                scale_ui = ease_out_back(min(1.0, (t_norm - 5.0) / 0.6), 1.3)
            elif t_norm < 7.0:
                scale_ui = 1.0 + 0.02 * math.sin((t_norm - 5.6) * 8.0)
            else:
                scale_ui = max(0.0, 1.0 - ease_in_cubic((t_norm - 7.0) / 0.5))

            if scale_ui > 0.05 and like_overlay is not None and sub_overlay is not None:
                w_like, h_like = int(like_overlay.shape[1] * scale_ui), int(like_overlay.shape[0] * scale_ui)
                w_sub, h_sub = int(sub_overlay.shape[1] * scale_ui), int(sub_overlay.shape[0] * scale_ui)
                gap = int(120 * scale_ui)
                total_w = w_like + gap + w_sub
                start_x, cy = width // 2 - total_w // 2, height // 2
                overlay_bgra(frame, cv2.resize(like_overlay, (w_like, h_like)), start_x, cy - h_like // 2)
                overlay_bgra(frame, cv2.resize(sub_overlay, (w_sub, h_sub)), start_x + w_like + gap, cy - h_sub // 2)

        # Stage 4: WhatsApp Banner (7.5 - 10.0)
        elif t_norm >= 7.5 and wa_overlay is not None:
            prog = min(1.0, (t_norm - 7.5) / 0.6)
            scale_wa = ease_out_back(prog, 1.3) * ((1.0 + 0.015 * math.sin((t_norm - 8.1) * 6.0)) if t_norm > 8.1 else 1.0)
            ww, wh = int(wa_overlay.shape[1] * scale_wa), int(wa_overlay.shape[0] * scale_wa)
            if ww > 4:
                overlay_bgra(frame, cv2.resize(wa_overlay, (ww, wh)), width//2 - ww//2, height//2 - wh//2)

        proc.stdin.write(frame.tobytes())
        if frame_idx % 60 == 0:
            gc.collect()

    proc.stdin.close()
    proc.wait()
    return output_path


# ==========================================
# 4. FAIL-SAFE MERGER FOR APP.PY
# ==========================================
def merge_intro_and_main(intro_mp4, main_mp4, final_output_mp4):
    """
    Concatenates intro and main video using filter_complex.
    Forces both streams into 48kHz stereo AAC and 1080p YUV420P to prevent
    audio dropping or desync regardless of original input formats.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", intro_mp4,
        "-i", main_mp4,
        "-filter_complex",
        "[0:v]scale=1920:1080,setsar=1,fps=30[v0];"
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a0];"
        "[1:v]scale=1920:1080,setsar=1,fps=30[v1];"
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        final_output_mp4
    ]
    subprocess.run(cmd, check=True)
    return final_output_mp4

