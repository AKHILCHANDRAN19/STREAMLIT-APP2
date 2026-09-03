import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import random
import datetime

# ==========================================
# CONFIGURATION & REPO ASSET PATHS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "Fonts")
IMAGES_DIR = os.path.join(BASE_DIR, "Images")

def smart_resize_and_crop(image, target_w=1280, target_h=300):
    """
    Scales and center-crops the image to fit exactly 1280x300 without stretching.
    """
    h, w = image.shape[:2]
    scale = max(target_w / w, target_h / h)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    start_x = max(0, (new_w - target_w) // 2)
    start_y = max(0, (new_h - target_h) // 2)

    return resized[start_y:start_y + target_h, start_x:start_x + target_w]


def draw_perfect_fit_text(draw, text, font_path, box_coords, text_color):
    """
    Maximizes font size aggressively to 98% width and 90% height for maximum bold impact.
    """
    x1, y1, x2, y2 = box_coords
    box_w = x2 - x1
    box_h = y2 - y1

    size = 250
    if not os.path.exists(font_path):
        print(f"Error: Font missing at {font_path}")
        return

    font = ImageFont.truetype(font_path, size)

    while size > 10:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        if w <= box_w * 0.98 and h <= box_h * 0.90:
            break
        size -= 1
        font = ImageFont.truetype(font_path, size)

    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    x = x1 + (box_w - w) / 2 - bbox[0]
    y = y1 + (box_h - h) / 2 - bbox[1]

    draw.text((x, y), text, font=font, fill=text_color)


def draw_date_and_live_icon(draw, date_str, font_path, box_coords):
    """
    Renders Box 2 with maximum possible scale (98% width / 88% height).
    """
    x1, y1, x2, y2 = box_coords
    box_w = x2 - x1
    box_h = y2 - y1

    size = 250
    if not os.path.exists(font_path):
        print(f"Error: Font missing at {font_path}")
        return

    live_text = "LIVE"
    end_text = " നിരക്ക്"

    while size > 10:
        font = ImageFont.truetype(font_path, size)

        bbox_date = draw.textbbox((0, 0), date_str, font=font)
        w_date = bbox_date[2] - bbox_date[0]
        h_date = bbox_date[3] - bbox_date[1]

        bbox_live = draw.textbbox((0, 0), live_text, font=font)
        w_live = bbox_live[2] - bbox_live[0]
        h_live = bbox_live[3] - bbox_live[1]

        bbox_end = draw.textbbox((0, 0), end_text, font=font)
        w_end = bbox_end[2] - bbox_end[0]
        h_end = bbox_end[3] - bbox_end[1]

        gap = int(size * 0.25)
        box_pad_x = int(size * 0.35)
        box_pad_y = int(size * 0.15)

        live_box_w = w_live + (box_pad_x * 2)
        live_box_h = h_live + (box_pad_y * 2)

        total_w = w_date + gap + live_box_w + w_end
        max_h = max(h_date, live_box_h, h_end)

        if total_w <= box_w * 0.98 and max_h <= box_h * 0.88:
            break
        size -= 1

    font = ImageFont.truetype(font_path, size)
    start_x = x1 + (box_w - total_w) / 2
    center_y = y1 + (box_h / 2)

    # 1. Draw Date
    date_y = center_y - (h_date / 2) - bbox_date[1]
    draw.text((start_x, date_y), date_str, font=font, fill=(255, 255, 255))

    # 2. Draw Red Rounded 'LIVE' Box
    current_x = start_x + w_date + gap
    rect_y1 = center_y - (live_box_h / 2)
    rect_y2 = center_y + (live_box_h / 2)
    rect_x1 = current_x
    rect_x2 = current_x + live_box_w

    draw.rounded_rectangle([rect_x1, rect_y1, rect_x2, rect_y2], radius=int(size * 0.12), fill=(230, 0, 0))

    live_x = rect_x1 + box_pad_x - bbox_live[0]
    live_y = center_y - (h_live / 2) - bbox_live[1]
    draw.text((live_x, live_y), live_text, font=font, fill=(255, 255, 255))

    # 3. Draw End Text
    current_x = rect_x2
    end_y = center_y - (h_end / 2) - bbox_end[1]
    draw.text((current_x, end_y), end_text, font=font, fill=(255, 255, 255))


def generate_thumbnail(top_banner_text, output_filename):
    width, height = 1280, 720
    
    font_extrabold = os.path.join(FONTS_DIR, "AnekMalayalam-ExtraBold.ttf")
    font_bold = os.path.join(FONTS_DIR, "AnekMalayalam-Bold.ttf")

    # Electric Yellow for high-contrast feed pop
    yellow_bg = [255, 230, 0]
    black_bg = [0, 0, 0]
    black_text = (0, 0, 0)
    white_text = (255, 255, 255)

    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    # Top Banners
    canvas[0:110, :] = yellow_bg
    canvas[110:210, :] = black_bg

    # Image Processing & Embedding (Color Grade + Unsharp Mask)
    image_inserted = False

    if os.path.exists(IMAGES_DIR):
        # specifically looking for numbered png files as requested
        png_files = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith('.png') and f[0].isdigit()]

        if png_files:
            selected_png = random.choice(png_files)
            img_path = os.path.join(IMAGES_DIR, selected_png)

            photo_bgr = cv2.imread(img_path)
            if photo_bgr is not None:
                # 1. Resize/Crop with Lanczos
                photo_resized = smart_resize_and_crop(photo_bgr, target_w=width, target_h=300)

                # 2. Boost Saturation (+25%)
                hsv = cv2.cvtColor(photo_resized, cv2.COLOR_BGR2HSV).astype(np.float32)
                hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.25, 0, 255)
                enhanced_bgr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

                # 3. Unsharp Masking Kernel for detail pop
                kernel = np.array([[0, -0.5, 0],
                                   [-0.5, 3, -0.5],
                                   [0, -0.5, 0]])
                sharpened_bgr = cv2.filter2D(enhanced_bgr, -1, kernel)

                photo_final_rgb = cv2.cvtColor(sharpened_bgr, cv2.COLOR_BGR2RGB)
                canvas[210:510, :] = photo_final_rgb
                image_inserted = True

    if not image_inserted:
        canvas[210:510, :] = [150, 150, 150]

    # Bottom Banners
    canvas[510:610, :] = black_bg
    canvas[610:720, :] = yellow_bg

    img_pil = Image.fromarray(canvas)
    draw = ImageDraw.Draw(img_pil)

    # Date Generation
    malayalam_months = {
        1: 'ജനുവരി', 2: 'ഫെബ്രുവരി', 3: 'മാർച്ച്', 4: 'ഏപ്രിൽ',
        5: 'മെയ്', 6: 'ജൂൺ', 7: 'ജൂലൈ', 8: 'ആഗസ്റ്റ്',
        9: 'സെപ്റ്റംബർ', 10: 'ഒക്ടോബർ', 11: 'നവംബർ', 12: 'ഡിസംബർ'
    }
    now = datetime.datetime.now()
    date_str = f"{now.day} {malayalam_months[now.month]} {now.year}"

    text3 = "കേരളത്തിൽ ഒരു പവന്റെ വില"
    text4 = "ഏറ്റവും പുതിയ വിപണി വാർത്തകൾ"

    # Box 1: Yellow BG -> Black Text (Full Scale)
    draw_perfect_fit_text(draw, top_banner_text, font_extrabold, (0, 0, width, 110), black_text)

    # Box 2: Black BG -> Date + LIVE Tag (Full Scale)
    draw_date_and_live_icon(draw, date_str, font_bold, (0, 110, width, 210))

    # Box 3: Black BG -> White Text (Full Scale)
    draw_perfect_fit_text(draw, text3, font_extrabold, (0, 510, width, 610), white_text)

    # Box 4: Yellow BG -> Black Text (Full Scale)
    draw_perfect_fit_text(draw, text4, font_extrabold, (0, 610, width, 720), black_text)

    # Save Output
    save_path = os.path.join(IMAGES_DIR, output_filename)
    try:
        img_pil.save(save_path, "PNG")
        print(f"Success! Thumbnail saved to: {save_path}")
    except Exception as e:
        print(f"Failed to save {output_filename}. Error: {e}")

def main():
    # Generate Thumbnail 1
    generate_thumbnail(
        top_banner_text="ഇന്നത്തെ സ്വർണ്ണവില കേരളം", 
        output_filename="thumbnail_1.png"
    )
    
    # Generate Thumbnail 2 (2nd Update)
    generate_thumbnail(
        top_banner_text="ഇന്നത്തെ രണ്ടാം സ്വർണ്ണവില കേരളം", 
        output_filename="thumbnail_2.png"
    )

if __name__ == "__main__":
    main()

