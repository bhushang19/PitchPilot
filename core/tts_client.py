"""Azure Speech text-to-speech client (audio-only narration).

Synthesizes one plain-audio clip per talking-script segment using the real-time
Text to Speech REST endpoint. No avatar, no polling: each request returns the
spoken audio directly, which the compositor plays over the screenshots.

Reference: https://learn.microsoft.com/azure/ai-services/speech-service/rest-text-to-speech
"""

import os
from xml.sax.saxutils import escape as xml_escape

import requests

# 24 kHz mono MP3 keeps files small and is read natively by MoviePy/ffmpeg.
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"


class NarrationSynthesisError(RuntimeError):
    pass


def _endpoint(config):
    """Real-time TTS host, derived from the Speech region."""
    region = (config.speech_region or "").strip()
    if not region:
        raise NarrationSynthesisError(
            "SPEECH_REGION is required for text-to-speech narration."
        )
    return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


def _build_ssml(text, voice):
    safe = xml_escape(text)
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        "xml:lang='en-US'>"
        f"<voice name='{voice}'>{safe}</voice>"
        "</speak>"
    )


def synthesize_clip(config, spoken_text, dest_path):
    """Synthesize one narration audio clip and save it to dest_path (mp3)."""
    ssml = _build_ssml(spoken_text, config.narration_voice)
    headers = {
        "Ocp-Apim-Subscription-Key": config.speech_key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
        "User-Agent": "pitchpilot",
    }
    resp = requests.post(_endpoint(config), data=ssml.encode("utf-8"), headers=headers)
    if resp.status_code >= 400:
        raise NarrationSynthesisError(
            f"Synthesis failed [{resp.status_code}]: {resp.text}"
        )
    with open(dest_path, "wb") as f:
        f.write(resp.content)
    return dest_path


def synthesize_segments(config, segments, clips_dir, on_progress=None):
    """Synthesize a narration clip per segment; return list of (segment, clip_path)."""
    os.makedirs(clips_dir, exist_ok=True)
    results = []
    total = len(segments)
    for idx, seg in enumerate(segments, start=1):
        text = (seg.get("spoken_text") or "").strip()
        if not text:
            continue
        dest = os.path.join(clips_dir, f"segment_{seg['order']:03d}.mp3")
        if on_progress:
            on_progress(idx, total, seg)
        synthesize_clip(config, text, dest)
        results.append((seg, dest))
    return results
