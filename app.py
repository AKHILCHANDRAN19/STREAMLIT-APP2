import streamlit as st
import asyncio
import threading
import os
import time
import subprocess
import collections
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message

# Import project modules
import intro
import thumbnail
import scrapping
# import price_22k
# import sevendayComparison

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
        # Load API credentials from Streamlit Secrets
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
                "• `/scrapeakg` — Today's 22K rate from AKGSMA (1g & 1 pavan)\n"
                "• `/scrapegd` — GoodReturns 22K rate & 8-day history\n"
                "• `/genthumb` — Generate high-contrast thumbnails\n"
                "• `/generate` — Render and upload intro video"
            )
            await message.reply_text(welcome_text)

        # ----------------------------------------------------
        # SCRAPE AKGSMA COMMAND
        # ----------------------------------------------------
        @app.on_message(filters.command("scrapeakg") & filters.private)
        async def handle_scrapeakg(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Fetching 22K Gold Data from AKGSMA...**")
            GLOBAL_STATE.set_status("Scraping", "Fetching AKGSMA live rate...")
            
            try:
                report = await asyncio.to_thread(scrapping.get_akgsma_report)
                await status_msg.edit_text(report)
                GLOBAL_STATE.set_status("Idle", "AKGSMA data retrieved successfully.")
                GLOBAL_STATE.log(f"Sent AKGSMA report to user {message.from_user.id}")
            except Exception as e:
                GLOBAL_STATE.log(f"AKGSMA Scrape Error: {e}")
                await status_msg.edit_text(f"❌ **Error fetching AKGSMA:** {e}")
                GLOBAL_STATE.set_status("Error", str(e))

        # ----------------------------------------------------
        # SCRAPE GOODRETURNS COMMAND
        # ----------------------------------------------------
        @app.on_message(filters.command("scrapegd") & filters.private)
        async def handle_scrapegd(client: Client, message: Message):
            status_msg = await message.reply_text("⏳ **Fetching 22K Gold Data from GoodReturns...**")
            GLOBAL_STATE.set_status("Scraping", "Fetching GoodReturns history...")
            
            try:
                report = await asyncio.to_thread(scrapping.get_goodreturns_report)
                await status_msg.edit_text(report)
                GLOBAL_STATE.set_status("Idle", "GoodReturns data retrieved successfully.")
                GLOBAL_STATE.log(f"Sent GoodReturns report to user {message.from_user.id}")
            except Exception as e:
                GLOBAL_STATE.log(f"GoodReturns Scrape Error: {e}")
                await status_msg.edit_text(f"❌ **Error fetching GoodReturns:** {e}")
                GLOBAL_STATE.set_status("Error", str(e))

        # ----------------------------------------------------
        # THUMBNAIL GENERATOR COMMAND
        # ----------------------------------------------------
        @app.on_message(filters.command("genthumb") & filters.private)
        async def handle_genthumb(client: Client, message: Message):
            status_msg = await message.reply_text("🖼️ **Generating Thumbnails...**")
            
            try:
                GLOBAL_STATE.set_status("Thumbnail", "Generating YouTube Thumbnails...")
                await asyncio.to_thread(thumbnail.main)
                
                thumb1_path = os.path.join("Images", "thumbnail_1.png")
                thumb2_path = os.path.join("Images", "thumbnail_2.png")
                
                if os.path.exists(thumb1_path):
                    await client.send_photo(
                        chat_id=message.chat.id,
                        photo=thumb1_path,
                        caption="🥇 **Thumbnail 1: ഇന്നത്തെ സ്വർണ്ണവില കേരളം**"
                    )
                
                if os.path.exists(thumb2_path):
                    await client.send_photo(
                        chat_id=message.chat.id,
                        photo=thumb2_path,
                        caption="🥇 **Thumbnail 2: ഇന്നത്തെ രണ്ടാം സ്വർണ്ണവില കേരളം**"
                    )
                
                await status_msg.delete()
                GLOBAL_STATE.set_status("Idle", "Thumbnails generated successfully.")
                GLOBAL_STATE.log("Thumbnails successfully uploaded to Telegram.")

            except Exception as e:
                GLOBAL_STATE.log(f"Thumbnail Error: {e}")
                await status_msg.edit_text(f"❌ **Error generating thumbnails:** {e}")
                GLOBAL_STATE.set_status("Error", str(e))

        # ----------------------------------------------------
        # VIDEO GENERATOR PIPELINE COMMAND
        # ----------------------------------------------------
        @app.on_message(filters.command("generate") & filters.private)
        async def handle_generate(client: Client, message: Message):
            status_msg = await message.reply_text("🔄 **Initializing Pipeline...**")
            
            try:
                # Render Intro
                GLOBAL_STATE.set_status("Rendering", "Generating Cinematic Intro...")
                await status_msg.edit_text("🎬 **Rendering 3D Intro Video...** (This takes a moment)")
                await asyncio.to_thread(intro.main)

                # Concatenate with FFmpeg
                GLOBAL_STATE.set_status("Merging", "Stitching video chunks via FFmpeg...")
                await status_msg.edit_text("🗜️ **Stitching final video...**")
                
                concat_file = os.path.join("Videos", "inputs.txt")
                final_output = os.path.join("Videos", "FINAL_UPLOAD.mp4")
                
                with open(concat_file, "w") as f:
                    f.write("file 'intro.mp4'\n")

                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
                    "-i", concat_file, "-c", "copy", final_output
                ]
                subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # Upload to Telegram
                GLOBAL_STATE.set_status("Uploading", "Sending final video to Telegram...")
                await status_msg.edit_text("⬆️ **Uploading final video to chat...**")
                
                await client.send_video(
                    chat_id=message.chat.id,
                    video=final_output,
                    caption="🥇 **ഇന്നത്തെ സ്വർണ്ണവില**\nHere is your generated video."
                )
                
                await status_msg.delete()
                GLOBAL_STATE.set_status("Idle", "Render complete. Waiting for next run.")
                GLOBAL_STATE.log("Video successfully uploaded to Telegram.")

            except Exception as e:
                GLOBAL_STATE.log(f"Pipeline Error: {e}")
                await status_msg.edit_text(f"❌ **Error during generation:** {e}")
                GLOBAL_STATE.set_status("Error", str(e))

        await app.start()
        GLOBAL_STATE.log("Bot authenticated and listening for commands.")
        
        # Keep background thread alive without touching OS signals
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

