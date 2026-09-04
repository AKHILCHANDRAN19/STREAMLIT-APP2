import os
import subprocess
from datetime import datetime, timedelta, timezone
import cv2

# IST Timezone (UTC+5:30)
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def get_current_ist_date():
    return datetime.now(IST_TIMEZONE)


def format_timestamp(seconds: float) -> str:
    """Converts seconds into standard YouTube chapter format (MM:SS)."""
    total_sec = max(0, int(round(seconds)))
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{mins:02d}:{secs:02d}"


def get_media_duration(file_path: str) -> float:
    """Safely extracts duration from any video or audio file."""
    if not file_path or not os.path.exists(file_path):
        return 0.0

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass

    try:
        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps > 0 and frame_count > 0:
            return frame_count / fps
    except Exception:
        pass

    return 0.0


# ==========================================
# 1. YOUTUBE TITLES (TYPE 1 & TYPE 2)
# ==========================================
def get_youtube_titles(dt=None):
    if dt is None:
        dt = get_current_ist_date()
    date_str = dt.strftime("%d-%m-%Y")

    title_1 = f"ഇന്നത്തെ സ്വർണ്ണവില | {date_str}|gold rate kerala today|gold rate today|#keralagolddesk"
    title_2 = f"ഇന്നത്തെ സ്വർണ്ണവില {date_str} | Kerala gold rate today | Gold rate Malayalam | Swarna vila"

    # Using single backticks for 1-tap copy without language-tag conflicts
    message = (
        "📌 **YOUTUBE TITLES (Tap to Copy)**\n"
        "──────────────────────────────\n\n"
        "**Title 1:**\n"
        f"`{title_1}`\n\n"
        "**Title 2:**\n"
        f"`{title_2}`"
    )
    return message, title_1, title_2


# ==========================================
# 2. YOUTUBE DESCRIPTION
# ==========================================
def get_youtube_description(dt=None, intro_dur=0.0, comp_dur=0.0, include_timestamps=True):
    if dt is None:
        dt = get_current_ist_date()
    date_str = dt.strftime("%d-%m-%Y")

    ts_block = ""
    if include_timestamps and (intro_dur > 0 or comp_dur > 0):
        ts_intro = "00:00"
        ts_comp = format_timestamp(intro_dur)
        ts_price = format_timestamp(intro_dur + comp_dur)
        ts_block = (
            f"\n⏱️ Timestamps / Chapters:\n"
            f"{ts_intro} - Introduction\n"
            f"{ts_comp} - 7-Day Gold Rate Trend (വിപണി വിശകലനം)\n"
            f"{ts_price} - Today's 22K Gold Rate (ഇന്നത്തെ സ്വർണ്ണവില)\n"
        )

    desc = f"""ഇന്നത്തെ സ്വർണ്ണവില {date_str} | Gold Rate Kerala Today | Kerala gold rate today | Gold rate Malayalam | gold 916 kerala | Swarna vila 

📲 വാട്സാപ്പ് ചാനലിൽ സൗജന്യമായി ജോയിൻ ചെയ്യാം: ലിങ്ക് ചാനലിന്റെ About സെക്ഷനിൽ ലഭ്യമാണ്!
👉 Join our WhatsApp Channel for Free (Link in Channel About Section)
{ts_block}
Gold Rate Kerala Today | Kerala gold rate today |  kerala gold rate | swarna vila | Gold rate today | Innathe swarna vila | Gold rate malayalam | Today Gold Rate Malayalam | സ്വർണ്ണവില | akgsma | kerala gold | Gold Rate Today Malayalam | gold rate in kerala | Rate of gold in kerala | swarnam vila | swarna villa | sornam vila | Swarna vila malayalam | today malayalam gold rate | today gold price | today in kerala gold price | today in kerala swarna vila | kerala today gold rate | today swarnam vila | gold price live | live gold rate india | tomorrow gold rate

#keralagoldratetoday
#keralagoldrate
#swaranavila
#goldratetoday
#innatheswarnavila
#goldratemalayalam
#goldratekeralatoday
#goldpricetoday
#goldratekerala
#goldratetodaymalayalam
#todaygoldrate
#swarnam
#keralagoldpricetoday
#goldkerala
#keralagold
#keralapricestoday
#goldkeralatoday
#todaygoldprice
#todaygoldpricemalayalam
#dailymalayalamgoldrate
#goldpricemalayalamtoday
#sornavilamalayalam
#malayalamgoldprice
#dailygoldrate
#goldratetodayinkerala
#keralaprices
#916goldratetoday
#jewellery
#goldmarketinindia
#today_gold_rate_in_kerala
#lifestyle
#unboxing
#goldratekeralaintoday
#malayalamgold
#goldmalayalam
#goldenkerala
#indiagoldrate
#kulus
#keralawedding
#todaymarketratekerala

Keywords:

kerala gold rate today
swarna vila
gold rate kerala
gold rate today malayalam
akgsma
LifeStyle
Fashion
Bridal
Wedding
jewellery
innathe swarna vila
sorna vila
swarna villa
sornam vila
sorna vila today
today swarna vila
innathe sorna vila
innathe gold rate
innathe gold vila
innathe gold rate kerala
gold price today
gold price
gold rate
gold vila
gold rate malayalam
gold kerala rate
kerala gold price today
today gold rate kerala
today gold rate in kerala
today gold rate
today gold price
today gold rate malayalam
gold rate kerala today
gold rate today kerala
gold rate today in kerala
today's gold rate
swarna vila today kerala
kerala
gold kerala
today's gold rate in kerala
innathe swarna vila malayalam
kerala swarna vila today
today kerala gold rate
gold rate in kerala
gold kerala rate today
kerala gold rate today 8 gram
kerala gold rate today 1 pavan
kerala gold rate today 916
kerala gold rate today malayalam
today gold rate in kerala news
today's gold rate in kerala 22k
gold today market rate kerala
kerala gold rate today kerala
gold rate today kerala malabar gold
gold rate today kerala gold
today's gold rate in kerala in gram
anogru rate today
today gold rate kerala kozhikode
today gold rate in kerala live
today gold rate in kerala manorama news
kerala gold price today in 916
kerala gold price 22 carat
today market rate kerala
gold price in kochi today
today gold price in kerala 1 gram
today gold rate in kerala price chart
today gold rate in kerala price of 1 pavan
today gold price in kerala palakkad
today gold price kerala 916
24 carat today gold price kerala
Today's gold price in kerala for 1 pavan
today's rate of gold
gold rate in kerala per gram
24 carat gold rate in kerala
22 carat gold rate in kerala
gold rate in kerala yesterday
live gold rate in kerala
jewelry gold rate in kerala
current gold rate in kerala
gold rate live in malayalam
gold rate per gram in malayalam
gold rate chart in malayalam"""

    # Multi-line code block with explicit newline
    message = f"```\n{desc}\n```"
    return message, desc


# ==========================================
# 3. YOUTUBE TAGS
# ==========================================
def get_youtube_tags():
    tags = "Gold Rate Malayalam, gold rate kerala today, gold 916 kerala, Kerala gold rate today, swarna vila, innathe gold rate, innathe swarna vila, kerala gold today, kerala gold price, akgsma, today gold price, today gold rate malayalam, swarna vila today, malayalam gold, സ്വർണ്ണ വില, ഇന്നത്തെ സ്വർണവില, gold news malayalam, swarnam rate today, LifeStyle, Gold Jewellery, wedding jewellery, Malappuram gold, Thrissur gold, Money, Fashion, jewellery design, Bridal, Necklace, Silver, gold"
    
    # Using single backticks for 1-tap copy
    message = (
        "🏷️ **YOUTUBE TAGS (Tap to Copy)**\n"
        "──────────────────────────────\n\n"
        f"`{tags}`"
    )
    return message, tags


# ==========================================
# 4. TELEGRAM ASYNC DISPATCHER (3 MESSAGES)
# ==========================================
async def send_youtube_metadata(client, chat_id, dt=None, intro_dur=0.0, comp_dur=0.0, include_timestamps=True):
    """Sends YouTube metadata in 3 distinct, 1-tap copyable messages."""
    title_msg, _, _ = get_youtube_titles(dt)
    desc_msg, _ = get_youtube_description(dt, intro_dur=intro_dur, comp_dur=comp_dur, include_timestamps=include_timestamps)
    tags_msg, _ = get_youtube_tags()

    # Message 1: Titles
    await client.send_message(chat_id=chat_id, text=title_msg)
    
    # Message 2: Description
    await client.send_message(chat_id=chat_id, text=desc_msg)
    
    # Message 3: Tags
    await client.send_message(chat_id=chat_id, text=tags_msg)
