import asyncio
import websockets
import requests
import json
import base64
import uuid
import wave
import os
import time

try:
    import streamlit as st
    from google import genai
    from google.genai import types
except ImportError:
    st = None
    genai = None

# ==========================================
# ⚙️ CONFIGURATION & VOICE SETUP
# ==========================================
# Vijay voice profile locked (Latha removed)
VIJAY_VOICE = {
    "name": "Vijay",
    "role": "Storytelling",
    "id": "374b80da-e622-4dfc-90f6-1eeb13d331c9",
    "gemini_voice": "Puck"  # High-energy male voice equivalent
}

# Global index tracker for round-robin rotation
CURRENT_KEY_INDEX = 0


def get_gemini_api_keys():
    """
    Extracts multiple Gemini API keys from Streamlit secrets or environment variables.
    Supports either comma-separated strings or TOML lists.
    """
    keys = []
    if st and hasattr(st, "secrets"):
        if "GEMINI_API_KEYS" in st.secrets:
            raw = st.secrets["GEMINI_API_KEYS"]
            if isinstance(raw, list):
                keys = [k.strip() for k in raw if k.strip()]
            elif isinstance(raw, str):
                keys = [k.strip() for k in raw.split(",") if k.strip()]
        elif "GEMINI_API_KEY" in st.secrets:
            keys = [st.secrets["GEMINI_API_KEY"].strip()]

    if not keys:
        env_raw = os.environ.get("GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEY", ""))
        keys = [k.strip() for k in env_raw.split(",") if k.strip()]

    return keys


def get_next_gemini_key(keys):
    """Cycles through the available API keys for each text request."""
    global CURRENT_KEY_INDEX
    if not keys:
        return None
    selected_key = keys[CURRENT_KEY_INDEX]
    CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % len(keys)
    return selected_key


def get_output_dir():
    """Routes output to local repo Audios folder or mobile storage if present."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    audios_dir = os.path.join(base_dir, "Audios")
    if os.path.exists("/storage/emulated/0/Download"):
        return "/storage/emulated/0/Download"
    os.makedirs(audios_dir, exist_ok=True)
    return audios_dir


def save_gemini_wave(filename, pcm_data, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)


# ==========================================
# 🟡 1. GEMINI PRIMARY TTS (ROTATING KEYS)
# ==========================================
async def generate_audio_gemini(text, api_key, output_filename=None):
    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "VALID_KEY"
    print(f"\n🚀 Sending text to Gemini API using Key [{masked_key}]...")

    try:
        client = genai.Client(api_key=api_key)
        res = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=VIJAY_VOICE["gemini_voice"]
                        )
                    )
                )
            )
        )

        audio_data = res.candidates[0].content.parts[0].inline_data.data
        out_dir = get_output_dir()
        file_path = output_filename or os.path.join(out_dir, f"vijay_gemini_{int(time.time())}.wav")

        save_gemini_wave(file_path, audio_data)
        print(f"✅ Gemini TTS complete for Vijay voice!")
        print(f"💾 Saved as: {file_path}")
        return file_path

    except Exception as e:
        print(f"❌ Gemini TTS failed on key [{masked_key}]: {e}")
        return None


# ==========================================
# ⚪ 2. CARTESIA FALLBACK (VIJAY ONLY)
# ==========================================
def get_cartesia_public_token():
    url = "https://backend.cartesia.ai/access-token/public"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        "Referer": "https://cartesia.ai/languages/malayalam"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        return data.get("token", data.get("access_token"))
    except Exception as e:
        print(f"❌ Failed to obtain Cartesia token: {e}")
        return None


async def generate_audio_cartesia(text, token, output_filename=None):
    ws_url = f"wss://api.cartesia.ai/tts/websocket?cartesia_version=2024-06-10&api_key={token}"

    payload = {
        "context_id": str(uuid.uuid4()),
        "model_id": "sonic-3",
        "transcript": text,
        "language": "ml",
        "voice": {
            "mode": "id",
            "id": VIJAY_VOICE["id"]
        },
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": 44100
        }
    }

    try:
        async with websockets.connect(ws_url) as ws:
            print(f"\n🚀 Sending text to Cartesia WebSocket (Vijay Voice)...")
            await ws.send(json.dumps(payload))

            audio_buffer = bytearray()
            while True:
                response = json.loads(await ws.recv())

                if response.get("type") == "chunk":
                    audio_buffer.extend(base64.b64decode(response["data"]))
                    print("📦 Streaming audio chunks...", end="\r")

                elif response.get("type") == "done":
                    out_dir = get_output_dir()
                    file_path = output_filename or os.path.join(out_dir, f"vijay_cartesia_{int(time.time())}.wav")

                    with wave.open(file_path, "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(44100)
                        wav_file.writeframes(audio_buffer)

                    print(f"\n✅ Cartesia TTS complete for Vijay voice!")
                    print(f"💾 Saved as: {file_path}")
                    return file_path

                elif response.get("type") == "error":
                    print(f"\n❌ Cartesia Server Error: {response.get('error')}")
                    return None

    except Exception as e:
        print(f"\n❌ Cartesia Connection Error: {e}")
        return None


# ==========================================
# 🚀 MAIN TTS DISPATCHER
# ==========================================
async def generate_speech(text, output_filename=None):
    """
    Main entrypoint: Rotates Gemini keys per request.
    Falls back to Cartesia (Vijay) if keys are missing or exhausted.
    """
    gemini_keys = get_gemini_api_keys()

    if gemini_keys and genai:
        current_key = get_next_gemini_key(gemini_keys)
        audio_path = await generate_audio_gemini(text, current_key, output_filename)
        if audio_path:
            return audio_path
        print("⚠️ Primary Gemini call failed. Falling back to Cartesia...")

    # Fallback Execution
    print("🔄 Engaging Cartesia fallback engine...")
    token = get_cartesia_public_token()
    if token:
        return await generate_audio_cartesia(text, token, output_filename)

    print("❌ All TTS providers failed.")
    return None


async def main():
    print("-" * 50)
    user_text = input("📝 Enter Malayalam text:\n> ").strip()
    print("-" * 50)

    if not user_text:
        user_text = "ഇന്നത്തെ സ്വർണ്ണവിപണി വിവരങ്ങളിലേക്ക് സ്വാഗതം."

    await generate_speech(user_text)


if __name__ == "__main__":
    asyncio.run(main())
