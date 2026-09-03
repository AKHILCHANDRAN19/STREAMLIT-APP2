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

# Import modular project engines
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
        self.log_history = collections.deque(maxlen=35)
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
st.title("🥇 Kerala Gold Desk - Automated Rendering Engine")

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
# 2. AUDIO & PIPELINE UTILITIES
# ==========================================
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

def get_audio_duration_seconds(wav_path: str) -> float:
    """Returns the exact float duration of a WAV file."""
    if not os.path.exists(wav_path):
        return 0.0
    with wave.open(wav_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)

def combine_wav_files(input_paths, output_path, pause_duration=0.6):
    """Losslessly stitches multiple PCM WAV buffers in pure Python."""
    data = []
    params = None
    for p in input_paths:
        if os.path.exists(p):
            with wave.open(p, "rb") as wf:
                if params is None:
                    params = wf.getparams()
                frames = wf.readframes(wf.getnframes())
                data.append(frames)
            if pause_duration > 0 and params:
                silence_frames = int(params.framerate * pause_duration)
                silence = b"\x00" * (silence_frames * params.sampwidth * params.nchannels)
                data.append(silence)
    if data and pause_duration > 0:
        data.pop()
    if data and params:
        with wave.open(output_path, "wb") as out_wf:
            out_wf.setparams(params)
            for chunk in data:
                out_wf.writeframes(chunk)

def clean_script_for_tts(raw_text: str):
    """Splits formatted script into clean sections for sequential TTS generation."""
    # Split by section dividers
    parts = raw_text.split("━━━━━━━━━━━━━━━━━━━━━━━━━")
    sections = []
    for part in parts:
        cleaned = re.sub(r"[\*\_━\#\(\)\:\-]", " ", part)
        cleaned = re.sub(r"[A-Za-z]+", "", cleaned)  # Strip English title tags
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > 15:
            sections.append(cleaned)
    return sections if sections else [raw_text]


# ==========================================
# 3. MASTER PIPELINE ORCHESTRATOR
# ==========================================
async def execute_full_production(client: Client, message: Message, source: str):
    """
    Orchestrates full production:
    Script -> Split TTS -> Intro -> 7-Day Comp -> 22K Price -> Single-pass FFmpeg Merge.
    """
    now = datetime.now(IST_TIMEZONE)
    date_label = now.strftime("%Y %B %d %A")
    final_video_name = f"Today Gold Rate Kerala {date_label}.mp4"
    
    videos_dir = os.path.join(os.getcwd(), "Videos")
    audios_dir = os.path.join(os.getcwd(), "Audios")
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(audios_dir, exist_ok=True)

    status_msg = await message.reply_text(f"🚀 **Starting {source.upper()} Production Pipeline...**")
    
    try:
        # STEP 1: SCRIPT GENERATION
        GLOBAL_STATE.set_status("Scripting", f"Scraping and composing {source} script...")
        await status_msg.edit_text("📜 **Step 1/6: Generating Malayalam Audio Script...**")
        
        if source == "akgsma":
            formatted_script = await asyncio.to_thread(script.get_script_akg)
        else:
            formatted_script = await asyncio.to_thread(script.get_script_gd)
            
        await message.reply_text(formatted_script)
        GLOBAL_STATE.log("Script dispatched to Telegram.")

        # STEP 2: SPLIT TTS GENERATION
        GLOBAL_STATE.set_status("TTS", "Generating sequential Malayalam voiceovers...")
        await status_msg.edit_text("🎙️ **Step 2/6: Synthesizing Voiceover (Rotating Keys)...**")
        
        text_sections = clean_script_for_tts(formatted_script)
        section_audio_paths = []
        for idx, sec_text in enumerate(text_sections):
            sec_out = os.path.join(audios_dir, f"section_{idx}_{int(now.timestamp())}.wav")
            audio_file = await tts.generate_speech(sec_text, output_filename=sec_out)
            if audio_file and os.path.exists(audio_file):
                section_audio_paths.append(audio_file)
            await asyncio.sleep(1.0)
            
        master_audio_path = os.path.join(audios_dir, f"master_voice_{int(now.timestamp())}.wav")
        combine_wav_files(section_audio_paths, master_audio_path, pause_duration=0.5)
        
        total_audio_duration = get_audio_duration_seconds(master_audio_path)
        GLOBAL_STATE.log(f"Audio synthesized. Total Duration: {total_audio_duration:.2f}s")
        
        await client.send_audio(
            chat_id=message.chat.id,
            audio=master_audio_path,
            caption=f"🎙️ **Master Malayalam Voiceover** ({total_audio_duration:.1f}s)"
        )

        # STEP 3: INTRO GENERATION
        GLOBAL_STATE.set_status("Rendering", "Generating 3D Intro...")
        await status_msg.edit_text("🎬 **Step 3/6: Rendering 3D Intro Video...**")
        await asyncio.to_thread(intro.main)
        intro_vid = os.path.join(videos_dir, "intro.mp4")
        if os.path.exists(intro_vid):
            await client.send_video(chat_id=message.chat.id, video=intro_vid, caption="🎬 **Intro Segment**")

        # STEP 4: 7-DAY COMPARISON GENERATION
        GLOBAL_STATE.set_status("Rendering", "Generating 7-Day Comparison...")
        await status_msg.edit_text("📊 **Step 4/6: Rendering 7-Day Comparison Chart...**")
        comp_vid = await asyncio.to_thread(sevendayComparison.main)
        if comp_vid and os.path.exists(comp_vid):
            await client.send_video(chat_id=message.chat.id, video=comp_vid, caption="📈 **7-Day Price Trend Segment**")

        # STEP 5: TODAY'S 22K PRICE CHART
        GLOBAL_STATE.set_status("Rendering", f"Generating Today's Price Chart ({source})...")
        await status_msg.edit_text("🥇 **Step 5/6: Rendering 3D Price Chart...**")
        price_vid = await asyncio.to_thread(price_22k.main, source=source)
        if price_vid and os.path.exists(price_vid):
            await client.send_video(chat_id=message.chat.id, video=price_vid, caption="💎 **Today's Rate Segment**")

        # STEP 6: SINGLE-PASS HIGH-SPEED FFMPEG MERGE
        GLOBAL_STATE.set_status("Merging", "Executing unified FFmpeg concatenation and audio binding...")
        await status_msg.edit_text("🗜️ **Step 6/6: Performing Single-Pass Master Stitching...**")

        final_output_path = os.path.join(videos_dir, final_video_name)

        # Filter complex: normalizes timebases/resolutions, concats video tracks, fades out, pads video to exact audio duration
        filter_complex = (
            "[0:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v0];"
            "[1:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v1];"
            "[2:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v2];"
            "[v0][v1][v2]concat=n=3:v=1:a=0[vconcat];"
            f"[vconcat]tpad=stop_mode=clone:stop_duration={max(1.0, total_audio_duration + 1.0)},fade=t=out:st={max(1.0, total_audio_duration - 1.0)}:d=1.0[vfinal]"
        )

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", intro_vid,
            "-i", comp_vid,
            "-i", price_vid,
            "-i", master_audio_path,
            "-filter_complex", filter_complex,
            "-map", "[vfinal]",
            "-map", "3:a",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            final_output_path
        ]

        await asyncio.to_thread(subprocess.run, ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # STEP 7: DISPATCH FINAL MASTER VIDEO
        if os.path.exists(final_output_path):
            await status_msg.edit_text("⬆️ **Uploading Final Master Production...**")
            caption_text = (
                f"🥇 **{final_video_name}**\n"
                f"📅 Date: `{date_label}`\n"
                f"🏛️ Source: `{source.upper()}`\n"
                f"🕒 Voiceover Duration: `{total_audio_duration:.1f}s`"
            )
            await client.send_video(
                chat_id=message.chat.id,
                video=final_output_path,
                caption=caption_text
            )
            await status_msg.delete()
            GLOBAL_STATE.set_status("Idle", "Master production complete.")
            GLOBAL_STATE.log(f"Dispatched master video: {final_video_name}")
        else:
            await status_msg.edit_text("❌ **FFmpeg compilation failed.**")

    except Exception as e:
        GLOBAL_STATE.log(f"Pipeline Failure: {e}")
        await status_msg.edit_text(f"❌ **Pipeline encountered an error:**\n`{e}`")
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
                "**Full Production Pipelines:**\n"
                "• `/genakg` — Complete Auto-Pipeline (AKGSMA Today + GoodReturns History)\n"
                "• `/gengd` — Complete Auto-Pipeline (GoodReturns All)\n\n"
                "**Stand-alone Video Renders:**\n"
                "• `/priceakg` — 3D Price Chart Video (AKGSMA)\n"
                "• `/pricegd` — 3D Price Chart Video (GoodReturns)\n"
                "• `/gencomp` — 3D 7-Day Comparison Video\n\n"
                "**Scraping & Utility:**\n"
                "• `/scriptakg` — Malayalam Script (AKGSMA)\n"
                "• `/scriptgd` — Malayalam Script (GoodReturns)\n"
                "• `/scrapeakg` — Raw Rate Card (AKGSMA)\n"
                "• `/scrapegd` — Raw Rate Card (GoodReturns)\n"
                "• `/genthumb` — YouTube Thumbnails\n"
                "• `/tts <text>` — Custom Voiceover"
            )
            await message.reply_text(welcome_text)

        # ----------------------------------------------------
        # COMPLETE PRODUCTION COMMANDS
        # ----------------------------------------------------
        @app.on_message(filters.command("genakg") & filters.private)
        async def handle_genakg(client: Client, message: Message):
            await execute_full_production(client, message, source="akgsma")

        @app.on_message(filters.command("gengd") & filters.private)
        async def handle_gengd(client: Client, message: Message):
            await execute_full_production(client, message, source="goodreturns")

        # ----------------------------------------------------
        # STAND-ALONE VIDEO GENERATORS
        # ----------------------------------------------------
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

        # ----------------------------------------------------
        # SCRIPT & TEXT COMMANDS
        # ----------------------------------------------------
        @app.on_message(filters.command("scriptakg") & filters.private)
        async def handle_scriptakg(client: Client, message: Message):
            s_text = await asyncio.to_thread(script.get_script_akg)
            await message.reply_text(s_text)

        @app.on_message(filters.command("scriptgd") & filters.private)
        async def handle_scriptgd(client: Client, message: Message):
            s_text = await asyncio.to_thread(script.get_script_gd)
            await message.reply_text(s_text)

        @app.on_message(filters.command("scrapeakg") & filters.private)
        async def handle_scrapeakg(client: Client, message: Message):
            r_text = await asyncio.to_thread(scrapping.get_akgsma_report)
            await message.reply_text(r_text)

        @app.on_message(filters.command("scrapegd") & filters.private)
        async def handle_scrapegd(client: Client, message: Message):
            r_text = await asyncio.to_thread(scrapping.get_goodreturns_report)
            await message.reply_text(r_text)

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
        GLOBAL_STATE.log("Pyrofork bot authenticated and listening.")
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

