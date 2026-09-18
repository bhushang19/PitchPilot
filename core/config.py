"""Configuration for the demo-video generator.

Reads the shared project `.env` (same file used by narrator.py) plus the extra
SPEECH_* / narration settings this feature needs. Azure OpenAI credentials are
reused to generate the organic talking script; the Azure Speech resource is used
for text-to-speech narration.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load the .env from the project root (one level up from this file), so the same
# credentials that drive narrator.py are reused here without duplication.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


def _get_bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_float(name, default):
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _parse_resolution(value, default=(1920, 1080)):
    if not value:
        return default
    try:
        w, h = value.lower().replace(" ", "").split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return default


@dataclass
class Config:
    """Resolved configuration for a single PitchPilot run."""

    # Azure OpenAI — used for app exploration and talking-script generation.
    openai_api_key: str = ""
    openai_endpoint: str = ""
    openai_deployment: str = ""
    openai_api_version: str = ""

    # Azure Speech resource — used for text-to-speech narration.
    speech_endpoint: str = ""
    speech_key: str = ""
    speech_region: str = ""

    # Narration voice (default is a broadly available prebuilt neural voice).
    narration_voice: str = "en-US-AvaMultilingualNeural"

    # Video composition.
    resolution: tuple = (1920, 1080)
    fps: int = 30
    enable_bg_music: bool = False
    bg_music_volume: float = 0.08

    # Extra fields kept for reference/debugging.
    extras: dict = field(default_factory=dict)

    @classmethod
    def load(cls):
        return cls(
            openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            openai_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_MODEL", ""),
            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", ""),
            speech_endpoint=(os.getenv("SPEECH_ENDPOINT", "") or "").rstrip("/"),
            speech_key=os.getenv("SPEECH_KEY", ""),
            speech_region=os.getenv("SPEECH_REGION", ""),
            narration_voice=(
                os.getenv("NARRATION_VOICE", "")
                or os.getenv("AVATAR_VOICE", "")
                or "en-US-AvaMultilingualNeural"
            ),
            resolution=_parse_resolution(os.getenv("VIDEO_RESOLUTION")),
            fps=int(_get_float("VIDEO_FPS", 30)),
            enable_bg_music=_get_bool("ENABLE_BG_MUSIC", False),
            bg_music_volume=_get_float("BG_MUSIC_VOLUME", 0.08),
        )

    def missing_for_script(self):
        """Env vars required to generate the talking script (Azure OpenAI)."""
        required = {
            "AZURE_OPENAI_API_KEY": self.openai_api_key,
            "AZURE_OPENAI_ENDPOINT": self.openai_endpoint,
            "AZURE_OPENAI_CHAT_DEPLOYMENT_MODEL": self.openai_deployment,
            "AZURE_OPENAI_API_VERSION": self.openai_api_version,
        }
        return [k for k, v in required.items() if not v]

    def missing_for_narration(self):
        """Env vars required to render the narration audio (Azure Speech)."""
        required = {
            "SPEECH_KEY": self.speech_key,
            "SPEECH_REGION": self.speech_region,
        }
        return [k for k, v in required.items() if not v]
