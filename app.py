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

# Import your modules
import intro
import thumbnail
# import Scrappping
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
        # Pull API credentials from Streamlit Cloud Secrets
        app = Client(
            "gold_bot_session",
            api_id=int(st.secrets["API_ID"]),
            api_hash=str(st.secrets["API_HASH"]),
            bot_token=str(st.secrets["BOT_TOKEN"]),
            in_memory=True
        )

        @app.on_message(filters.command("start") & filters.private)
        async def handle_start(client: Client, message: Message):
            await message.reply_text(
                "👋 **Kerala Gold Desk Bot Online.**\n\n"
                "Available Commands:\n"
                "• `/generate` - Render full intro video\n"
                "• `/genthumb` - Generate YouTube thumbnails"
            )

        @app.on_message(filters.command("genthumb") & filters.private)
        async def handle_genthumb(client: Client, message: Message):
            status_msg = await message.reply_text("🖼️ **Generating Thumbnails...**")
            
            try:
                GLOBAL_STATE.set_status("Thumbnail", "Generating YouTube Thumbnails...")
                thumbnail.main() 
                
                thumb1_path = os.path.join("Images", "thumbnail_1.png")
                thumb2_path = os.path.join("Images", "thumbnail_2.png")
                
                # Upload Thumbnail 1
                if os.path.exists(thumb1_path):
                    await client.send_photo(
                        chat_id=message.chat.id,
                        photo=thumb1_path,
                        caption="🥇 **Thumbnail 1: ഇന്നത്തെ സ്വർണ്ണവില കേരളം**"
                    )
                
                # Upload Thumbnail 2
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

        @app.on_message(filters.command("generate") & filters.private)
        async def handle_generate(client: Client, message: Message):
            status_msg = await message.reply_text("🔄 **Initializing Pipeline...**")
            
            try:
                # STEP 1: Scraping
                GLOBAL_STATE.set_status("Scraping", "Fetching latest gold prices...")
                await status_msg.edit_text("🔄 **Scraping latest market data...**")
                # Scrappping.main() # Execute your scraping logic

                # STEP 2: Render Intro
                GLOBAL_STATE.set_status("Rendering", "Generating Cinematic Intro...")
                await status_msg.edit_text("🎬 **Rendering 3D Intro Video...** (This takes a moment)")
                intro.main() 

                # STEP 3: Render Daily Price & 7-Day Comparison
                # price_22k.main()
                # sevendayComparison.main()

                # STEP 4: FFmpeg Concatenation
                GLOBAL_STATE.set_status("Merging", "Stitching video chunks via FFmpeg...")
                await status_msg.edit_text("🗜️ **Stitching final video...**")
                
                concat_file = os.path.join("Videos", "inputs.txt")
                final_output = os.path.join("Videos", "FINAL_UPLOAD.mp4")
                
                with open(concat_file, "w") as f:
                    f.write("file 'intro.mp4'\n")
                    # f.write("file '22k_price.mp4'\n")
                    # f.write("file 'sevenday_comparison.mp4'\n")

                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
                    "-i", concat_file, "-c", "copy", final_output
                ]
                subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # STEP 5: Upload to Telegram
                GLOBAL_STATE.set_status("Uploading", "Sending final video to Telegram...")
                await status_msg.edit_text("⬆️ **Uploading final video to chat...**")
                
                await client.send_video(
                    chat_id=message.chat.id,
                    video=final_output,
                    caption="🥇 **ഇന്നത്തെ സ്വർണ്ണവില**\nHere is your generated video.",
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
        
        # THE MAGIC FIX: Keeps thread alive without triggering OS signals
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

