import asyncio
import websockets
import json
import base64
import uuid
import wave
import os
import time
import numpy as np
from curl_cffi import requests

try:
    import streamlit as st
    from google import genai
    from google.genai import types
except ImportError:
    st = None
    genai = None

VIJAY_VOICE = {
    "name": "Vijay",
    "role": "Storytelling",
    "id": "374b80da-e622-4dfc-90f6-1eeb13d331c9",
    "gemini_voice": "Puck"
}

CURRENT_KEY_INDEX = 0
CACHED_CARTESIA_TOKEN = None
TOKEN_EXPIRY = 0


def get_gemini_api_keys():
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
    global CURRENT_KEY_INDEX
    if not keys:
        return None
    selected_key = keys[CURRENT_KEY_INDEX]
    CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % len(keys)
    return selected_key


def get_output_dir():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    audios_dir = os.path.join(base_dir, "Audios")
    os.makedirs(audios_dir, exist_ok=True)
    return audios_dir


def save_gemini_wave(filename, pcm_data, channels=1, orig_rate=24000, target_rate=44100, sample_width=2):
    """Saves Gemini audio and automatically resamples it to 44.1kHz standard."""
    if orig_rate != target_rate:
        samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
        target_len = int(len(samples) * target_rate / float(orig_rate))
        indices = np.linspace(0, len(samples) - 1, target_len)
        resampled = np.interp(indices, np.arange(len(samples)), samples).astype(np.int16)
        pcm_data = resampled.tobytes()
        rate = target_rate
    else:
        rate = orig_rate

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)


async def generate_audio_gemini(text, api_key, output_filename=None):
    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "VALID_KEY"
    try:
        client = genai.Client(api_key=api_key)
        # Using native async .aio client to avoid blocking the bot loop
        res = await client.aio.models.generate_content(
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
        file_path = output_filename or os.path.join(out_dir, f"gemini_{int(time.time()*1000)}.wav")
        save_gemini_wave(file_path, audio_data, orig_rate=24000, target_rate=44100)
        return file_path
    except Exception as e:
        print(f"⚠️ Gemini key [{masked_key}] failed / rate-limited: {e}", flush=True)
        return None


def get_cartesia_public_token(force_refresh=False):
    global CACHED_CARTESIA_TOKEN, TOKEN_EXPIRY
    now = time.time()
    
    if not force_refresh and CACHED_CARTESIA_TOKEN and now < TOKEN_EXPIRY:
        return CACHED_CARTESIA_TOKEN

    if st and hasattr(st, "secrets") and "CARTESIA_API_KEY" in st.secrets:
        return st.secrets["CARTESIA_API_KEY"].strip()
    if os.environ.get("CARTESIA_API_KEY"):
        return os.environ.get("CARTESIA_API_KEY").strip()

    url = "https://backend.cartesia.ai/access-token/public"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://cartesia.ai/languages/malayalam",
        "Origin": "https://cartesia.ai",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        res = requests.get(url, headers=headers, impersonate="chrome120", timeout=12)
        if res.status_code == 200:
            data = res.json()
            token = data.get("token", data.get("access_token"))
            if token:
                CACHED_CARTESIA_TOKEN = token
                # Short cache (60s) so dead tokens are never held for 15 minutes!
                TOKEN_EXPIRY = now + 60
                return token
        return None
    except Exception as e:
        print(f"❌ Failed to fetch Cartesia token: {e}", flush=True)
        return None


async def generate_audio_cartesia(text, output_filename=None):
    global CACHED_CARTESIA_TOKEN
    
    token = get_cartesia_public_token(force_refresh=False)
    if not token:
        token = get_cartesia_public_token(force_refresh=True)
        if not token:
            return None

    ws_url = f"wss://api.cartesia.ai/tts/websocket?cartesia_version=2024-06-10&api_key={token}"
    payload = {
        "context_id": str(uuid.uuid4()),
        "model_id": "sonic-3",
        "transcript": text,
        "language": "ml",
        "voice": {"mode": "id", "id": VIJAY_VOICE["id"]},
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": 44100
        }
    }

    try:
        async with websockets.connect(ws_url, close_timeout=10) as ws:
            await ws.send(json.dumps(payload))
            audio_buffer = bytearray()
            while True:
                response = json.loads(await ws.recv())
                if response.get("type") == "chunk":
                    audio_buffer.extend(base64.b64decode(response["data"]))
                elif response.get("type") == "done":
                    out_dir = get_output_dir()
                    file_path = output_filename or os.path.join(out_dir, f"cartesia_{int(time.time()*1000)}.wav")
                    with wave.open(file_path, "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(44100)
                        wav_file.writeframes(audio_buffer)
                    return file_path
                elif response.get("type") == "error":
                    print(f"⚠️ Cartesia token invalid/exhausted: {response.get('error')}", flush=True)
                    # Instantly invalidate dead token so next run doesn't reuse it!
                    CACHED_CARTESIA_TOKEN = None
                    return None
    except Exception as e:
        print(f"⚠️ Cartesia connection dropped: {e}", flush=True)
        CACHED_CARTESIA_TOKEN = None
        return None


async def generate_speech(text, output_filename=None):
    """
    1. Tries all Gemini keys in rotation (skipping exhausted ones).
    2. Falls back to Cartesia (auto-invalidating expired tokens).
    """
    gemini_keys = get_gemini_api_keys()

    # Step 1: Loop through all Gemini keys on 429 rate limit
    if gemini_keys and genai:
        for _ in range(len(gemini_keys)):
            key = get_next_gemini_key(gemini_keys)
            audio_path = await generate_audio_gemini(text, key, output_filename)
            if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                return audio_path

    # Step 2: Fallback to Cartesia with fresh token retry
    audio_path = await generate_audio_cartesia(text, output_filename)
    if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
        return audio_path

    # Step 3: If token expired, force a fresh token fetch and retry once
    token_fresh = get_cartesia_public_token(force_refresh=True)
    if token_fresh:
        audio_path = await generate_audio_cartesia(text, output_filename)
        if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
            return audio_path

    print(f"🚨 Both Gemini and Cartesia failed for: '{text[:35]}...'", flush=True)
    return None
