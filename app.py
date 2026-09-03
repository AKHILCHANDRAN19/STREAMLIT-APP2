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
# 2. AUDIO & VIDEO UTILITIES
# ==========================================
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

def get_audio_duration_seconds(wav_path: str) -> float:
    """Returns the exact float duration of a WAV file."""
    if not os.path.exists(wav_path):
        return 0.0
    try:
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 0.0

def combine_wav_files(input_paths, output_path, pause_duration=0.4):
    """Losslessly stitches PCM WAV files in pure Python."""
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

def split_script_into_chunks(raw_text: str):
    """
    Splits script into 3 chunks for 7-day comparison and 2 chunks for today's price.
    """
    parts = raw_text.split("━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # 1. Comparison section (Part 1)
    comp_raw = parts[1] if len(parts) > 1 else ""
    comp_cleaned = re.sub(r"[#*_━]", "", comp_raw)
    comp_cleaned = comp_cleaned.replace("🥇", "").replace("ഇന്നത്തെ സ്വർണ്ണവില", "").strip()
    
    # Split comparison into 3 chunks: Intro/Trade, Weekly High/Low, Weekly Summary
    comp_chunks = []
    if "കഴിഞ്ഞ ഒരാഴ്ചത്തെ" in comp_cleaned:
        c1, rest = comp_cleaned.split("കഴിഞ്ഞ ഒരാഴ്ചത്തെ", 1)
        comp_chunks.append(c1.strip())
        if "ചുരുക്കത്തിൽ" in rest:
            c2, c3 = rest.split("ചുരുക്കത്തിൽ", 1)
            comp_chunks.append("കഴിഞ്ഞ ഒരാഴ്ചത്തെ " + c2.strip())
            comp_chunks.append("ചുരുക്കത്തിൽ " + c3.strip())
        else:
            comp_chunks.append("കഴിഞ്ഞ ഒരാഴ്ചത്തെ " + rest.strip())
    else:
        comp_chunks = [comp_cleaned] if comp_cleaned else ["സ്വർണ്ണവിപണി വിവരങ്ങളിലേക്ക് സ്വാഗതം."]

    # 2. Today's price section (Part 2)
    price_raw = parts[2] if len(parts) > 2 else ""
    price_cleaned = re.sub(r"[#*_━]", "", price_raw).strip()
    
    price_chunks = []
    if "ഇതോടെ" in price_cleaned:
        p1, p2 = price_cleaned.split("ഇതോടെ", 1)
        price_chunks.append(p1.strip())
        price_chunks.append("ഇതോടെ " + p2.strip())
    else:
        price_chunks = [price_cleaned] if price_cleaned else ["ഇന്നത്തെ സ്വർണ്ണവില മാറ്റമില്ലാതെ തുടരുന്നു."]

    return comp_chunks, price_chunks


# ==========================================
# 3. MASTER PIPELINE ORCHESTRATOR
# ==========================================
async def execute_full_production(client: Client, message: Message, source: str):
    now = datetime.now(IST_TIMEZONE)
    date_label = now.strftime("%Y %B %d %A")
    final_video_name = f"Today Gold Rate Kerala {date_label}.mp4"
    
    base_dir = os.getcwd()
    videos_dir = os.path.join(base_dir, "Videos")
    audios_dir = os.path.join(base_dir, "Audios")
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(audios_dir, exist_ok=True)

    status_msg = await message.reply_text(f"🚀 **Starting {source.upper()} Automated Pipeline...**")
    
    try:
        # STEP 1: SCRIPT GENERATION & DISPATCH
        GLOBAL_STATE.set_status("Scripting", f"Generating {source} Malayalam script...")
        await status_msg.edit_text("📜 **1/7: Generating Script...**")
        
        if source == "akgsma":
            formatted_script = await asyncio.to_thread(script.get_script_akg)
        else:
            formatted_script = await asyncio.to_thread(script.get_script_gd)
            
        await message.reply_text(formatted_script)
        GLOBAL_STATE.log(f"Script sent for {source}.")

        # STEP 2: SPLIT AUDIO GENERATION
        GLOBAL_STATE.set_status("TTS", "Synthesizing voiceovers...")
        await status_msg.edit_text("🎙️ **2/7: Generating Audio (3 calls for Comp, 2 calls for Price)...**")
        
        comp_chunks, price_chunks = split_script_into_chunks(formatted_script)
        ts = int(now.timestamp())
        
        # 7-Day Comparison Voiceover (3 Split API Calls)
        comp_audio_parts = []
        for i, chunk in enumerate(comp_chunks):
            part_path = os.path.join(audios_dir, f"comp_part_{i}_{ts}.wav")
            out_file = await tts.generate_speech(chunk, output_filename=part_path)
            if out_file and os.path.exists(out_file):
                comp_audio_parts.append(out_file)
            await asyncio.sleep(0.8)
            
        audio_comp_path = os.path.join(audios_dir, f"audio_7day_comp_{ts}.wav")
        combine_wav_files(comp_audio_parts, audio_comp_path, pause_duration=0.4)
        dur_comp = get_audio_duration_seconds(audio_comp_path)
        
        # Today's 22K Price Voiceover (2 Split API Calls)
        price_audio_parts = []
        for j, chunk in enumerate(price_chunks):
            part_path = os.path.join(audios_dir, f"price_part_{j}_{ts}.wav")
            out_file = await tts.generate_speech(chunk, output_filename=part_path)
            if out_file and os.path.exists(out_file):
                price_audio_parts.append(out_file)
            await asyncio.sleep(0.8)
            
        audio_price_path = os.path.join(audios_dir, f"audio_22k_price_{ts}.wav")
        combine_wav_files(price_audio_parts, audio_price_path, pause_duration=0.4)
        dur_price = get_audio_duration_seconds(audio_price_path)

        # Dispatch both audios to Telegram
        await client.send_audio(
            chat_id=message.chat.id,
            audio=audio_comp_path,
            caption=f"🎙️ **7-Day Comparison Audio** ({dur_comp:.1f}s)"
        )
        await client.send_audio(
            chat_id=message.chat.id,
            audio=audio_price_path,
            caption=f"🎙️ **Today's 22K Price Audio** ({dur_price:.1f}s)"
        )
        GLOBAL_STATE.log(f"Audios generated. Comp: {dur_comp:.1f}s | Price: {dur_price:.1f}s")

        # STEP 3: 3D INTRO VIDEO (COMPRESSED & FAST-START)
        GLOBAL_STATE.set_status("Rendering", "Generating 3D Intro Video...")
        await status_msg.edit_text("🎬 **3/7: Rendering 3D Intro...**")
        await asyncio.to_thread(intro.main)
        
        raw_intro = os.path.join(videos_dir, "intro.mp4")
        optimized_intro = os.path.join(videos_dir, f"intro_optimized_{ts}.mp4")
        
        # Optimize intro size (fixes 24MB size bloat and 0:00 duration display)
        intro_opt_cmd = [
            "ffmpeg", "-y", "-i", raw_intro,
            "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart", optimized_intro
        ]
        await asyncio.to_thread(subprocess.run, intro_opt_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        intro_disp = optimized_intro if os.path.exists(optimized_intro) else raw_intro
        await client.send_video(chat_id=message.chat.id, video=intro_disp, caption="🎬 **Intro Segment**")

        # STEP 4: 7-DAY COMPARISON (MATCHED TO COMP AUDIO DURATION)
        GLOBAL_STATE.set_status("Rendering", "Rendering 7-Day Comparison Video...")
        await status_msg.edit_text("📊 **4/7: Rendering 7-Day Comparison Chart...**")
        raw_comp_vid = await asyncio.to_thread(sevendayComparison.main)
        
        comp_final_vid = os.path.join(videos_dir, f"comp_final_{ts}.mp4")
        pad_dur_1 = max(0.5, dur_comp + 0.5)
        fade_st_1 = max(0.1, dur_comp - 0.6)
        
        # Mux Audio 1 & extend last frame to exact audio duration with fadeout
        comp_sync_cmd = [
            "ffmpeg", "-y", "-i", raw_comp_vid, "-i", audio_comp_path,
            "-filter_complex",
            f"[0:v]settb=AVTB,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={pad_dur_1},fade=t=out:st={fade_st_1}:d=0.6[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-t", str(dur_comp), "-movflags", "+faststart", comp_final_vid
        ]
        await asyncio.to_thread(subprocess.run, comp_sync_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await client.send_video(chat_id=message.chat.id, video=comp_final_vid, caption=f"📈 **7-Day Comparison Segment** ({dur_comp:.1f}s)")

        # STEP 5: TODAY'S 22K PRICE (MATCHED TO PRICE AUDIO DURATION)
        GLOBAL_STATE.set_status("Rendering", "Rendering 22K Price Video...")
        await status_msg.edit_text("💎 **5/7: Rendering Today's 22K Price Chart...**")
        raw_price_vid = await asyncio.to_thread(price_22k.main, source=source)
        
        price_final_vid = os.path.join(videos_dir, f"price_final_{ts}.mp4")
        pad_dur_2 = max(0.5, dur_price + 0.5)
        fade_st_2 = max(0.1, dur_price - 0.6)
        
        # Mux Audio 2 & extend last frame to exact audio duration with fadeout
        price_sync_cmd = [
            "ffmpeg", "-y", "-i", raw_price_vid, "-i", audio_price_path,
            "-filter_complex",
            f"[0:v]settb=AVTB,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={pad_dur_2},fade=t=out:st={fade_st_2}:d=0.6[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-t", str(dur_price), "-movflags", "+faststart", price_final_vid
        ]
        await asyncio.to_thread(subprocess.run, price_sync_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await client.send_video(chat_id=message.chat.id, video=price_final_vid, caption=f"💎 **Today's Rate Segment** ({dur_price:.1f}s)")

        # STEP 6: SINGLE-PASS MASTER MERGE
        GLOBAL_STATE.set_status("Merging", "Executing unified single-pass concatenation...")
        await status_msg.edit_text("🗜️ **6/7: Executing Single-Pass Fast Stitching...**")
        
        final_output_path = os.path.join(videos_dir, final_video_name)
        
        # Clean concat without re-rendering or audio loss
        concat_filter = (
            "[0:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v0];"
            "[1:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v1];"
            "[2:v]settb=AVTB,setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v2];"
            "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0];"
            "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];"
            "[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a2];"
            "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[vfinal][afinal]"
        )

        single_pass_ffmpeg = [
            "ffmpeg", "-y",
            "-i", intro_disp,
            "-i", comp_final_vid,
            "-i", price_final_vid,
            "-filter_complex", concat_filter,
            "-map", "[vfinal]", "-map", "[afinal]",
            "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            final_output_path
        ]
        await asyncio.to_thread(subprocess.run, single_pass_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # STEP 7: DISPATCH FINAL MASTER VIDEO
        if os.path.exists(final_output_path):
            await status_msg.edit_text("⬆️ **7/7: Uploading Final Production...**")
            file_mb = os.path.getsize(final_output_path) / (1024 * 1024)
            caption_text = (
                f"🥇 **{final_video_name}**\n"
                f"📅 `{date_label}`\n"
                f"🏛️ Source: `{source.upper()}`\n"
                f"📦 Size: `{file_mb:.1f} MB`"
            )
            await client.send_video(
                chat_id=message.chat.id,
                video=final_output_path,
                caption=caption_text
            )
            await status_msg.delete()
            GLOBAL_STATE.set_status("Idle", "Production successfully completed.")
            GLOBAL_STATE.log(f"Dispatched: {final_video_name} ({file_mb:.1f} MB)")
        else:
            await status_msg.edit_text("❌ **Error: Final output file was not generated.**")

    except Exception as e:
        GLOBAL_STATE.log(f"Pipeline Error: {e}")
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
                "• `/genakg` — Complete Pipeline (AKGSMA Today + GoodReturns History)\n"
                "• `/gengd` — Complete Pipeline (GoodReturns All)\n\n"
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

