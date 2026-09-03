import streamlit as st
import asyncio
import threading
import os
import subprocess
import collections
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message

# Import project modules
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
        self.log_history = collections.deque(maxlen=30)
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
# 2. PYROGRAM BOT LOGIC (BACKGROUND THREAD)
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
                "👋 **Kerala Gold Desk Bot Online.**\n\n"
                "**Available Commands:**\n"
                "• `/priceakg` — Render 3D Price Chart (AKGSMA)\n"
                "• `/pricegd` — Render 3D Price Chart (GoodReturns)\n"
                "• `/scrapeakg` — Live 22K rate from AKGSMA\n"
                "• `/scrapegd` — GoodReturns 22K rate & history\n"
                "• `/scriptakg` — Malayalam Script (AKGSMA)\n"
                "• `/scriptgd` — Malayalam Script (GoodReturns)\n"
                "• `/gencomp` — 3D 7-Day Comparison Video\n"
                "• `/genthumb` — YouTube Thumbnails\n"
                "• `/tts <text>` — Malayalam Voiceover\n"
                "• `/generate` — Full Video Pipeline"
            )
            await message.reply_text(welcome_text)

        # ----------------------------------------------------
        # 3D DAILY PRICE VIDEO COMMANDS
        # ----------------------------------------------------
        @app.on_message(filters.command("priceakg") & filters.private)
        async def handle_priceakg(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Rendering 3D Price Chart (AKGSMA)...**")
            GLOBAL_STATE.set_status("Rendering", "Generating AKGSMA price chart...")
            try:
                vid_path = await asyncio.to_thread(price_22k.main, source="akgsma")
                if vid_path and os.path.exists(vid_path):
                    await status_msg.edit_text("⬆️ **Uploading Video...**")
                    await client.send_video(chat_id=message.chat.id, video=vid_path, caption="📊 **22K Gold Price Update (AKGSMA)**")
                    await status_msg.delete()
                    GLOBAL_STATE.set_status("Idle", "Video uploaded.")
                else:
                    await status_msg.edit_text("❌ **Failed to render video.**")
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {e}")

        @app.on_message(filters.command("pricegd") & filters.private)
        async def handle_pricegd(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Rendering 3D Price Chart (GoodReturns)...**")
            GLOBAL_STATE.set_status("Rendering", "Generating GoodReturns price chart...")
            try:
                vid_path = await asyncio.to_thread(price_22k.main, source="goodreturns")
                if vid_path and os.path.exists(vid_path):
                    await status_msg.edit_text("⬆️ **Uploading Video...**")
                    await client.send_video(chat_id=message.chat.id, video=vid_path, caption="📊 **22K Gold Price Update (GoodReturns)**")
                    await status_msg.delete()
                    GLOBAL_STATE.set_status("Idle", "Video uploaded.")
                else:
                    await status_msg.edit_text("❌ **Failed to render video.**")
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {e}")

        # ----------------------------------------------------
        # 7-DAY COMPARISON VIDEO COMMAND (/gencomp)
        # ----------------------------------------------------
        @app.on_message(filters.command("gencomp") & filters.private)
        async def handle_gencomp(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Rendering 3D 7-Day Comparison Video...**")
            GLOBAL_STATE.set_status("Rendering", "Generating 7-day comparison animation...")
            try:
                video_path = await asyncio.to_thread(sevendayComparison.main)
                if video_path and os.path.exists(video_path):
                    await status_msg.edit_text("⬆️ **Uploading Comparison Video...**")
                    await client.send_video(
                        chat_id=message.chat.id,
                        video=video_path,
                        caption="📈 **22K Gold 7-Day Price Comparison**\n• Kerala Market Trend & High/Low Analysis"
                    )
                    await status_msg.delete()
                    GLOBAL_STATE.set_status("Idle", "Comparison video uploaded.")
                else:
                    await status_msg.edit_text("❌ **Failed to render comparison video.**")
                    GLOBAL_STATE.set_status("Error", "Comparison rendering failed.")
            except Exception as e:
                GLOBAL_STATE.log(f"Gencomp Error: {e}")
                await status_msg.edit_text(f"❌ **Error generating comparison video:** {e}")
                GLOBAL_STATE.set_status("Error", str(e))

        # ----------------------------------------------------
        # TTS GENERATOR COMMAND
        # ----------------------------------------------------
        @app.on_message(filters.command("tts") & filters.private)
        async def handle_tts(client: Client, message: Message):
            if len(message.text.split()) < 2:
                return await message.reply_text("❌ **Usage:** `/tts <Malayalam text>`")
            
            user_text = message.text.split(maxsplit=1)[1]
            status_msg = await message.reply_text("🗣️ **Generating Voiceover...**")
            GLOBAL_STATE.set_status("TTS", "Generating audio via Gemini/Cartesia...")
            try:
                audio_path = await tts.generate_speech(user_text)
                if audio_path and os.path.exists(audio_path):
                    await client.send_audio(chat_id=message.chat.id, audio=audio_path, caption=f"🎙️ **Generated Audio:**\n`{user_text}`")
                    await status_msg.delete()
                    GLOBAL_STATE.set_status("Idle", "Audio generated successfully.")
                else:
                    await status_msg.edit_text("❌ **Failed to generate audio.**")
                    GLOBAL_STATE.set_status("Error", "TTS generation failed.")
            except Exception as e:
                GLOBAL_STATE.log(f"TTS Error: {e}")
                await status_msg.edit_text(f"❌ **Error:** {e}")
                GLOBAL_STATE.set_status("Error", str(e))

        # ----------------------------------------------------
        # SCRIPT GENERATORS
        # ----------------------------------------------------
        @app.on_message(filters.command("scriptakg") & filters.private)
        async def handle_scriptakg(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Generating Malayalam Script (AKGSMA)...**")
            try:
                script_text = await asyncio.to_thread(script.get_script_akg)
                await status_msg.edit_text(script_text)
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {e}")

        @app.on_message(filters.command("scriptgd") & filters.private)
        async def handle_scriptgd(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Generating Malayalam Script (GoodReturns)...**")
            try:
                script_text = await asyncio.to_thread(script.get_script_gd)
                await status_msg.edit_text(script_text)
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {e}")

        # ----------------------------------------------------
        # SCRAPE COMMANDS
        # ----------------------------------------------------
        @app.on_message(filters.command("scrapeakg") & filters.private)
        async def handle_scrapeakg(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Fetching AKGSMA Data...**")
            try:
                report = await asyncio.to_thread(scrapping.get_akgsma_report)
                await status_msg.edit_text(report)
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {e}")

        @app.on_message(filters.command("scrapegd") & filters.private)
        async def handle_scrapegd(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Fetching GoodReturns Data...**")
            try:
                report = await asyncio.to_thread(scrapping.get_goodreturns_report)
                await status_msg.edit_text(report)
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {e}")

        # ----------------------------------------------------
        # THUMBNAIL GENERATOR
        # ----------------------------------------------------
        @app.on_message(filters.command("genthumb") & filters.private)
        async def handle_genthumb(client: Client, message: Message):
            status_msg = await message.reply_text("🖼️ **Generating Thumbnails...**")
            try:
                await asyncio.to_thread(thumbnail.main)
                t1 = os.path.join("Images", "thumbnail_1.png")
                t2 = os.path.join("Images", "thumbnail_2.png")
                if os.path.exists(t1):
                    await client.send_photo(chat_id=message.chat.id, photo=t1, caption="🥇 **Thumbnail 1**")
                if os.path.exists(t2):
                    await client.send_photo(chat_id=message.chat.id, photo=t2, caption="🥇 **Thumbnail 2**")
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ **Error:** {e}")

        # ----------------------------------------------------
        # FULL PIPELINE GENERATOR
        # ----------------------------------------------------
        @app.on_message(filters.command("generate") & filters.private)
        async def handle_generate(client: Client, message: Message):
            status_msg = await message.reply_text("🔄 **Initializing Full Video Pipeline...**")
            try:
                GLOBAL_STATE.set_status("Rendering", "Generating Intro...")
                await status_msg.edit_text("🎬 **Rendering 3D Intro Video...**")
                await asyncio.to_thread(intro.main)

                GLOBAL_STATE.set_status("Rendering", "Generating 7-Day Comparison...")
                await status_msg.edit_text("📊 **Rendering 7-Day Comparison...**")
                await asyncio.to_thread(sevendayComparison.main)

                GLOBAL_STATE.set_status("Merging", "Stitching video segments via FFmpeg...")
                await status_msg.edit_text("🗜️ **Stitching final video chunks...**")
                
                concat_file = os.path.join("Videos", "inputs.txt")
                final_output = os.path.join("Videos", "FINAL_UPLOAD.mp4")
                
                with open(concat_file, "w") as f:
                    f.write("file 'intro.mp4'\n")
                    f.write("file 'sevenday_comparison.mp4'\n")

                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
                    "-i", concat_file, "-c", "copy", final_output
                ]
                subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                await status_msg.edit_text("⬆️ **Uploading final video to Telegram...**")
                await client.send_video(
                    chat_id=message.chat.id,
                    video=final_output,
                    caption="🥇 **ഇന്നത്തെ സ്വർണ്ണവില റിപ്പോർട്ട്**\nIntro & 7-Day Market Trend"
                )
                await status_msg.delete()
                GLOBAL_STATE.set_status("Idle", "Pipeline complete.")
            except Exception as e:
                GLOBAL_STATE.log(f"Pipeline Error: {e}")
                await status_msg.edit_text(f"❌ **Error:** {e}")
                GLOBAL_STATE.set_status("Error", str(e))

        await app.start()
        GLOBAL_STATE.log("Bot connected and listening for commands.")
        await asyncio.Event().wait()

    except Exception as e:
        GLOBAL_STATE.log(f"CRITICAL CRASH: {e}")
    finally:
        if 'app' in locals() and app.is_initialized:
            await app.stop()

# ==========================================
# 3. STREAMLIT BOOTSTRAPPER
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

