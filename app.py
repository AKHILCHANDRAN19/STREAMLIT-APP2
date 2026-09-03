import streamlit as st
import asyncio
import threading
import os
import re
import wave
import subprocess
import collections
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters
from pyrogram.types import Message

# Modular project sub-engines
import intro
import thumbnail
import scrapping
import tts
import script
import sevendayComparison
import price_22k

# ==========================================
# 1. STREAMLIT UI & TELEMETRY
# ==========================================
class TelemetryState:
    def __init__(self):
        self.log_history = collections.deque(maxlen=40)
        self.current_status = {"task": "Idle", "details": "Waiting for Telegram commands..."}

    def log(self, text: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {text}"
        self.log_history.append(entry)
        print(entry, flush=True)

    def set_status(self, task: str, details: str):
        self.current_status["task"] = task
        self.current_status["details"] = details

@st.cache_resource
def get_telemetry():
    return TelemetryState()

GLOBAL_STATE = get_telemetry()

st.set_page_config(page_title="Gold Video Bot", page_icon="🥇", layout="wide")
st.title("🥇 Kerala Gold Desk - Automated Production Engine")

col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("Engine Status")
    st.metric(label="Current Phase", value=GLOBAL_STATE.current_status["task"])
    st.info(GLOBAL_STATE.current_status["details"])

with col2:
    st.subheader("Live Telemetry Console")
    log_area = st.empty()
    log_area.code("\n".join(GLOBAL_STATE.log_history) if GLOBAL_STATE.log_history else "System ready.", language="text")

# ==========================================
# 2. AUDIO & TEXT UTILITIES
# ==========================================
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

def get_audio_duration_seconds(wav_path: str) -> float:
    if not os.path.exists(wav_path):
        return 0.0
    try:
        with wave.open(wav_path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0

def combine_wav_files(input_paths, output_path, pause_duration=0.25):
    data = []
    params = None
    for p in input_paths:
        if os.path.exists(p):
            with wave.open(p, "rb") as wf:
                if params is None:
                    params = wf.getparams()
                data.append(wf.readframes(wf.getnframes()))
            if pause_duration > 0 and params:
                silence_frames = int(params.framerate * pause_duration)
                data.append(b"\x00" * (silence_frames * params.sampwidth * params.nchannels))
    if data and pause_duration > 0:
        data.pop()
    if data and params:
        with wave.open(output_path, "wb") as out_wf:
            out_wf.setparams(params)
            for chunk in data:
                out_wf.writeframes(chunk)

def split_script_into_chunks(raw_text: str):
    parts = raw_text.split("━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # 1. 7-Day Comparison (Part 1)
    comp_raw = parts[1] if len(parts) > 1 else ""
    comp_clean = re.sub(r"🥇.*", "", comp_raw, flags=re.DOTALL)
    comp_clean = re.sub(r"[*_━#()|]", "", comp_clean).strip()

    comp_chunks = []
    if "കഴിഞ്ഞ ഒരാഴ്ചത്തെ" in comp_clean:
        c1, rest = comp_clean.split("കഴിഞ്ഞ ഒരാഴ്ചത്തെ", 1)
        comp_chunks.append(c1.strip())
        if "ചുരുക്കത്തിൽ" in rest:
            c2, c3 = rest.split("ചുരുക്കത്തിൽ", 1)
            comp_chunks.append("കഴിഞ്ഞ ഒരാഴ്ചത്തെ " + c2.strip())
            comp_chunks.append("ചുരുക്കത്തിൽ " + c3.strip())
        else:
            comp_chunks.append("കഴിഞ്ഞ ഒരാഴ്ചത്തെ " + rest.strip())
    else:
        sentences = [s.strip() for s in re.split(r"[.!?]", comp_clean) if len(s.strip()) > 5]
        comp_chunks = sentences[:3] if len(sentences) >= 3 else [comp_clean]

    # 2. Today's Price (Part 2)
    price_raw = parts[2] if len(parts) > 2 else ""
    price_clean = re.sub(r"[*_━#()|]", "", price_raw).strip()

    price_chunks = []
    if "ഇതോടെ" in price_clean:
        p1, p2 = price_clean.split("ഇതോടെ", 1)
        price_chunks.append(p1.strip())
        price_chunks.append("ഇതോടെ " + p2.strip())
    else:
        sentences = [s.strip() for s in re.split(r"[.!?]", price_clean) if len(s.strip()) > 5]
        price_chunks = sentences[:2] if len(sentences) >= 2 else [price_clean]

    return comp_chunks, price_chunks

def clean_intro_audios_dir(audios_dir: str):
    if not os.path.exists(audios_dir):
        return
    for fname in os.listdir(audios_dir):
        if fname.startswith(("comp_", "price_", "master_", "section_")) and fname.endswith(".wav"):
            try:
                os.remove(os.path.join(audios_dir, fname))
            except Exception:
                pass

# ==========================================
# 3. MASTER PRODUCTION PIPELINE
# ==========================================
async def execute_full_production(client: Client, message: Message, source: str):
    now = datetime.now(IST_TIMEZONE)
    date_label = now.strftime("%Y %B %d %A")
    final_video_name = f"Today Gold Rate Kerala {date_label}.mp4"

    base_dir = os.getcwd()
    videos_dir = os.path.join(base_dir, "Videos")
    intro_audios_dir = os.path.join(base_dir, "Audios")
    tts_audios_dir = os.path.join(base_dir, "TTS_Audios")

    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(intro_audios_dir, exist_ok=True)
    os.makedirs(tts_audios_dir, exist_ok=True)

    clean_intro_audios_dir(intro_audios_dir)

    status_msg = await message.reply_text(f"🚀 **Starting {source.upper()} Auto-Production Pipeline...**")

    try:
        # STEP 1: SCRIPT GENERATION
        GLOBAL_STATE.set_status("Scripting", f"Generating {source} Malayalam script...")
        await status_msg.edit_text("📜 **1/6: Generating Malayalam Script...**")
        formatted_script = await asyncio.to_thread(script.get_script_akg if source == "akgsma" else script.get_script_gd)
        await message.reply_text(formatted_script)
        GLOBAL_STATE.log(f"Script sent for {source}.")

        # STEP 2: CONCURRENT PARALLEL TTS (10-12s Total)
        GLOBAL_STATE.set_status("TTS", "Synthesizing voiceovers concurrently...")
        await status_msg.edit_text("🎙️ **2/6: Synthesizing Split Voiceovers in Parallel...**")
        comp_chunks, price_chunks = split_script_into_chunks(formatted_script)
        ts = int(now.timestamp())

        comp_tasks = [
            tts.generate_speech(chunk, output_filename=os.path.join(tts_audios_dir, f"comp_p{i}_{ts}.wav"))
            for i, chunk in enumerate(comp_chunks)
        ]
        price_tasks = [
            tts.generate_speech(chunk, output_filename=os.path.join(tts_audios_dir, f"price_p{j}_{ts}.wav"))
            for j, chunk in enumerate(price_chunks)
        ]

        comp_results, price_results = await asyncio.gather(
            asyncio.gather(*comp_tasks),
            asyncio.gather(*price_tasks)
        )

        comp_parts = [p for p in comp_results if p and os.path.exists(p)]
        price_parts = [p for p in price_results if p and os.path.exists(p)]

        audio_comp = os.path.join(tts_audios_dir, f"comp_audio_{ts}.wav")
        combine_wav_files(comp_parts, audio_comp, pause_duration=0.25)
        dur_comp = get_audio_duration_seconds(audio_comp)

        audio_price = os.path.join(tts_audios_dir, f"price_audio_{ts}.wav")
        combine_wav_files(price_parts, audio_price, pause_duration=0.25)
        dur_price = get_audio_duration_seconds(audio_price)

        await client.send_audio(chat_id=message.chat.id, audio=audio_comp, caption=f"🎙️ **7-Day Comparison Voiceover** ({dur_comp:.1f}s)")
        await client.send_audio(chat_id=message.chat.id, audio=audio_price, caption=f"🎙️ **Today's Rate Voiceover** ({dur_price:.1f}s)")
        GLOBAL_STATE.log(f"Voiceovers ready. Comp: {dur_comp:.1f}s | Price: {dur_price:.1f}s")

        # STEP 3: 3D INTRO VIDEO (Compresses to ~2MB with faststart directly in app.py)
        GLOBAL_STATE.set_status("Rendering", "Rendering 3D Intro Video...")
        await status_msg.edit_text("🎬 **3/6: Rendering 3D Intro Video...**")
        await asyncio.to_thread(intro.main)

        raw_intro = os.path.join(videos_dir, "intro.mp4")
        optimized_intro = os.path.join(videos_dir, f"intro_opt_{ts}.mp4")

        intro_cmd = [
            "ffmpeg", "-y", "-i", raw_intro,
            "-c:v", "libx264", "-crf", "24", "-preset", "veryfast",
            "-b:v", "1500k", "-maxrate", "1800k", "-bufsize", "3000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart", optimized_intro
        ]
        await asyncio.to_thread(subprocess.run, intro_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await client.send_video(chat_id=message.chat.id, video=optimized_intro, caption="🎬 **Intro Segment**")

        # STEP 4: 7-DAY COMPARISON (Runs in 2s, Extended via Native FFmpeg Filter)
        GLOBAL_STATE.set_status("Rendering", f"Rendering 7-Day Chart ({dur_comp:.1f}s)...")
        await status_msg.edit_text("📊 **4/6: Processing 7-Day Comparison Chart...**")
        raw_comp = await asyncio.to_thread(sevendayComparison.main)

        synced_comp = os.path.join(videos_dir, f"comp_synced_{ts}.mp4")
        pad_dur_1 = max(0.5, dur_comp - 5.5 + 0.5)
        fade_st_1 = max(0.1, dur_comp - 0.6)

        comp_sync_cmd = [
            "ffmpeg", "-y", "-i", raw_comp, "-i", audio_comp,
            "-filter_complex",
            f"[0:v]settb=AVTB,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={pad_dur_1},fade=t=out:st={fade_st_1}:d=0.6[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
            "-b:v", "1800k", "-maxrate", "2200k", "-bufsize", "4000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-t", str(dur_comp), "-movflags", "+faststart", synced_comp
        ]
        await asyncio.to_thread(subprocess.run, comp_sync_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await client.send_video(chat_id=message.chat.id, video=synced_comp, caption=f"📈 **7-Day Price Comparison** ({dur_comp:.1f}s)")

        # STEP 5: 22K PRICE CHART (Runs in 2s, Extended via Native FFmpeg Filter)
        GLOBAL_STATE.set_status("Rendering", f"Rendering 22K Price ({dur_price:.1f}s)...")
        await status_msg.edit_text("💎 **5/6: Processing Today's Rate Chart...**")
        raw_price = await asyncio.to_thread(price_22k.main, source=source)

        synced_price = os.path.join(videos_dir, f"price_synced_{ts}.mp4")
        pad_dur_2 = max(0.5, dur_price - 7.0 + 0.5)
        fade_st_2 = max(0.1, dur_price - 0.6)

        price_sync_cmd = [
            "ffmpeg", "-y", "-i", raw_price, "-i", audio_price,
            "-filter_complex",
            f"[0:v]settb=AVTB,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={pad_dur_2},fade=t=out:st={fade_st_2}:d=0.6[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
            "-b:v", "1800k", "-maxrate", "2200k", "-bufsize", "4000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-t", str(dur_price), "-movflags", "+faststart", synced_price
        ]
        await asyncio.to_thread(subprocess.run, price_sync_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await client.send_video(chat_id=message.chat.id, video=synced_price, caption=f"💎 **Today's Rate Segment** ({dur_price:.1f}s)")

        # STEP 6: SINGLE-PASS MASTER MERGE (Clean Concat Under 8 MB)
        GLOBAL_STATE.set_status("Merging", "Executing single-pass concatenation...")
        await status_msg.edit_text("🗜️ **6/6: Performing Master Video Assembly...**")

        final_video_path = os.path.join(videos_dir, final_video_name)
        concat_filter = (
            "[0:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v0];"
            "[1:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v1];"
            "[2:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v2];"
            "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0];"
            "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];"
            "[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a2];"
            "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[vfinal][afinal]"
        )

        master_cmd = [
            "ffmpeg", "-y",
            "-i", optimized_intro,
            "-i", synced_comp,
            "-i", synced_price,
            "-filter_complex", concat_filter,
            "-map", "[vfinal]", "-map", "[afinal]",
            "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
            "-b:v", "1800k", "-maxrate", "2200k", "-bufsize", "4000k",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            final_video_path
        ]
        await asyncio.to_thread(subprocess.run, master_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(final_video_path):
            file_mb = os.path.getsize(final_video_path) / (1024 * 1024)
            await client.send_video(
                chat_id=message.chat.id,
                video=final_video_path,
                caption=f"🥇 **{final_video_name}**\n📅 `{date_label}`\n🏛️ Source: `{source.upper()}`\n📦 Size: `{file_mb:.1f} MB`"
            )
            await status_msg.delete()
            GLOBAL_STATE.set_status("Idle", "Master production complete.")
            GLOBAL_STATE.log(f"Production Complete: {final_video_name} ({file_mb:.1f} MB)")
        else:
            await status_msg.edit_text("❌ **Error: Final compilation failed.**")

    except Exception as e:
        GLOBAL_STATE.log(f"Pipeline Crash: {e}")
        await status_msg.edit_text(f"❌ **Error:** `{e}`")
        GLOBAL_STATE.set_status("Error", str(e))

# ==========================================
# 4. PYROGRAM BOT ROUTING
# ==========================================
async def run_bot():
    try:
        app = Client(
            "gold_bot_session",
            api_id=int(st.secrets["API_ID"]),
            api_hash=str(st.secrets["API_HASH"]),
            bot_token=str(st.secrets["BOT_TOKEN"]),
            in_memory=True
        )

        @app.on_message(filters.command("start") & filters.private)
        async def handle_start(client: Client, message: Message):
            welcome_text = (
                "👋 **Kerala Gold Desk Production Engine**\n\n"
                "**Full Pipelines:**\n"
                "• `/genakg` — Master Video (AKGSMA Today + GoodReturns History)\n"
                "• `/gengd` — Master Video (GoodReturns All)\n\n"
                "**Standalone Video Renders:**\n"
                "• `/priceakg` — 3D Daily Rate Video (AKGSMA)\n"
                "• `/pricegd` — 3D Daily Rate Video (GoodReturns)\n"
                "• `/gencomp` — 3D 7-Day Comparison Video\n\n"
                "**Utilities:**\n"
                "• `/scriptakg` — Audio Script (AKGSMA)\n"
                "• `/scriptgd` — Audio Script (GoodReturns)\n"
                "• `/scrapeakg` — Market Rates (AKGSMA)\n"
                "• `/scrapegd` — Market Rates (GoodReturns)\n"
                "• `/genthumb` — YouTube Thumbnails\n"
                "• `/tts <text>` — Custom Voiceover"
            )
            await message.reply_text(welcome_text)

        @app.on_message(filters.command("genakg") & filters.private)
        async def handle_genakg(client: Client, message: Message):
            await execute_full_production(client, message, source="akgsma")

        @app.on_message(filters.command("gengd") & filters.private)
        async def handle_gengd(client: Client, message: Message):
            await execute_full_production(client, message, source="goodreturns")

        @app.on_message(filters.command("priceakg") & filters.private)
        async def handle_priceakg(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Rendering 3D Price Chart (AKGSMA)...**")
            vid_path = await asyncio.to_thread(price_22k.main, source="akgsma")
            if vid_path and os.path.exists(vid_path):
                await client.send_video(chat_id=message.chat.id, video=vid_path, caption="📊 **22K Gold Price (AKGSMA)**")
                await status_msg.delete()

        @app.on_message(filters.command("pricegd") & filters.private)
        async def handle_pricegd(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Rendering 3D Price Chart (GoodReturns)...**")
            vid_path = await asyncio.to_thread(price_22k.main, source="goodreturns")
            if vid_path and os.path.exists(vid_path):
                await client.send_video(chat_id=message.chat.id, video=vid_path, caption="📊 **22K Gold Price (GoodReturns)**")
                await status_msg.delete()

        @app.on_message(filters.command("gencomp") & filters.private)
        async def handle_gencomp(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Rendering 3D 7-Day Comparison...**")
            vid_path = await asyncio.to_thread(sevendayComparison.main)
            if vid_path and os.path.exists(vid_path):
                await client.send_video(chat_id=message.chat.id, video=vid_path, caption="📈 **7-Day Price Comparison**")
                await status_msg.delete()

        @app.on_message(filters.command("scriptakg") & filters.private)
        async def handle_scriptakg(client: Client, message: Message):
            await message.reply_text(await asyncio.to_thread(script.get_script_akg))

        @app.on_message(filters.command("scriptgd") & filters.private)
        async def handle_scriptgd(client: Client, message: Message):
            await message.reply_text(await asyncio.to_thread(script.get_script_gd))

        @app.on_message(filters.command("scrapeakg") & filters.private)
        async def handle_scrapeakg(client: Client, message: Message):
            await message.reply_text(await asyncio.to_thread(scrapping.get_akgsma_report))

        @app.on_message(filters.command("scrapegd") & filters.private)
        async def handle_scrapegd(client: Client, message: Message):
            await message.reply_text(await asyncio.to_thread(scrapping.get_goodreturns_report))

        @app.on_message(filters.command("genthumb") & filters.private)
        async def handle_genthumb(client: Client, message: Message):
            await asyncio.to_thread(thumbnail.main)
            t1 = os.path.join("Images", "thumbnail_1.png")
            t2 = os.path.join("Images", "thumbnail_2.png")
            if os.path.exists(t1):
                await client.send_photo(chat_id=message.chat.id, photo=t1, caption="🥇 **Thumbnail 1**")
            if os.path.exists(t2):
                await client.send_photo(chat_id=message.chat.id, photo=t2, caption="🥇 **Thumbnail 2**")

        @app.on_message(filters.command("tts") & filters.private)
        async def handle_tts(client: Client, message: Message):
            if len(message.text.split()) < 2:
                return await message.reply_text("❌ **Usage:** `/tts <Malayalam text>`")
            u_text = message.text.split(maxsplit=1)[1]
            a_path = await tts.generate_speech(u_text)
            if a_path and os.path.exists(a_path):
                await client.send_audio(chat_id=message.chat.id, audio=a_path, caption=f"🎙️ `{u_text}`")

        await app.start()
        GLOBAL_STATE.log("Bot active and listening for commands.")
        await asyncio.Event().wait()

    except Exception as e:
        GLOBAL_STATE.log(f"CRITICAL CRASH: {e}")
    finally:
        if "app" in locals() and app.is_initialized:
            await app.stop()

# ==========================================
# 5. STREAMLIT BOOTSTRAPPER
# ==========================================
@st.cache_resource
def start_background_bot():
    def run_async_loop():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_bot())
        except Exception as e:
            GLOBAL_STATE.log(f"Thread error: {e}")

    threading.Thread(target=run_async_loop, daemon=True).start()

start_background_bot()

