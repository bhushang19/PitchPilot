"""Stage 3 — render the narrated MP4 from talking-script segments.

Synthesizes one Azure Text-to-Speech clip per segment and composites them over
the screenshots into demo-video.mp4, written into the same run folder as the
transcript. Ported from the reference video generator's render path.
"""

import json
import os
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_MUSIC_DIR = os.path.join(_REPO_ROOT, "assets", "music")
_AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")


def _find_music():
    if not os.path.isdir(_MUSIC_DIR):
        return None
    for name in sorted(os.listdir(_MUSIC_DIR)):
        if name.lower().endswith(_AUDIO_EXTS):
            return os.path.join(_MUSIC_DIR, name)
    return None


def render_video(config, segments, run_dir, app_slug, dry_run=False):
    """Synthesize narration (unless dry-run) and compose the MP4 into run_dir."""
    out_path = os.path.join(run_dir, "demo-video.mp4")

    # Import the compositor (and TTS client) lazily so transcript-only runs don't
    # require MoviePy/ffmpeg to be installed.
    from core.compositor import build_video

    if dry_run:
        print("Dry run: skipping Azure narration, silent preview.")
        rendered = [(seg, None) for seg in segments]
    else:
        from core.tts_client import synthesize_segments

        clips_dir = os.path.join(run_dir, "clips")

        def _progress(idx, total, seg):
            label = seg.get("name") or seg.get("kind")
            print(f"  Synthesizing narration audio {idx}/{total}: {label}")

        rendered = synthesize_segments(config, segments, clips_dir, _progress)

    music_path = _find_music() if config.enable_bg_music else None
    if config.enable_bg_music:
        print(f"Background music: {music_path or 'none found in assets/music'}")

    print("Composing final video (this can take a while)...")
    build_video(config, rendered, out_path, music_path=music_path, dry_run=dry_run)
    print(f"\nDone. Video written to: {out_path}")

    # Stable pointer to the newest run's video for this app.
    latest_path = os.path.join(os.path.dirname(run_dir), "latest.txt")
    rel = os.path.join(os.path.basename(run_dir), "demo-video.mp4")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(rel + "\n")
    print(f"Latest-run pointer: {latest_path}")


def render_from_script(config, from_script, dry_run=False):
    """Re-render a video from an existing talking-script.json (no scrape/LLM)."""
    if not os.path.isfile(from_script):
        print(f"Talking-script not found: {from_script!r}")
        return
    try:
        with open(from_script, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = data.get("segments") or []
        if not segments:
            print("No segments in talking-script. Nothing to render.")
            return
        run_dir = os.path.dirname(os.path.abspath(from_script))
        app_slug = os.path.basename(os.path.dirname(run_dir))
        print(f"Re-rendering {len(segments)} segment(s) from: {from_script}")
        print(f"Run folder: {run_dir}")
        render_video(config, segments, run_dir, app_slug, dry_run)
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
