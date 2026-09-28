"""Slice the recorded exploration session into per-feature video clips.

Stage 1 records the whole headed Playwright session to `video/session.webm`. Each
feature's screenshot was taken right after that page settled, so the screenshot's
modification time marks the moment the feature was on screen. We cut the session
video at those timestamps to produce one short clip per feature, aligned with the
narration segment that describes it. Clips are re-encoded to MP4 for stable playback
in MoviePy. When no recording exists (or a cut is unusable) the segment simply keeps
its screenshot and the compositor falls back to the Ken Burns still.
"""

import glob
import logging
import os
import subprocess

_log = logging.getLogger(__name__)

# Minimum clip length; anything shorter is dropped so the compositor uses the still.
_MIN_CLIP_SECONDS = 0.6
# Small lead so a clip doesn't start exactly on the previous cut boundary.
_DEFAULT_LEAD_SECONDS = 2.5


def _ffmpeg_exe():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _find_session_video(run_dir):
    video_dir = os.path.join(run_dir, "video")
    session = os.path.join(video_dir, "session.webm")
    if os.path.isfile(session):
        return session
    candidates = glob.glob(os.path.join(video_dir, "*.webm"))
    return max(candidates, key=os.path.getmtime) if candidates else None


def _video_duration(path):
    try:
        from moviepy import VideoFileClip

        clip = VideoFileClip(path)
        try:
            return float(clip.duration or 0.0)
        finally:
            clip.close()
    except Exception:
        return 0.0


def _slice(ffmpeg, src, start, duration, out_path):
    """Re-encode [start, start+duration] of src into out_path (video only)."""
    cmd = [
        ffmpeg, "-y",
        "-i", src,
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    proc = subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    if proc.returncode != 0 or not os.path.isfile(out_path):
        _log.warning(
            "[slice] ffmpeg failed for %s: %s",
            os.path.basename(out_path),
            (proc.stderr or "").strip()[-300:],
        )
        return False
    return True


def attach_clips(run_dir, segments):
    """Cut the session video into per-feature clips and set seg['clip'] on each.

    `segments` is the talking-script segment list (dicts with 'kind', 'screenshot').
    Mutates the feature segments in place, adding a 'clip' path when a usable clip was
    produced. Returns the number of clips created.
    """
    session = _find_session_video(run_dir)
    if not session:
        _log.info("[slice] No session recording found; keeping screenshot stills.")
        return 0

    duration = _video_duration(session)
    if duration <= 0:
        _log.warning("[slice] Could not read session video duration; keeping stills.")
        return 0

    t0 = os.path.getctime(session)
    feats = [
        s for s in segments
        if s.get("kind") == "feature"
        and s.get("screenshot")
        and os.path.isfile(s["screenshot"])
    ]
    if not feats:
        return 0

    # Absolute cut points (seconds into the video) from screenshot mtimes.
    marks = []
    for seg in feats:
        mark = os.path.getmtime(seg["screenshot"]) - t0
        marks.append(max(0.0, min(mark, duration)))

    clips_dir = os.path.join(run_dir, "video", "clips")
    os.makedirs(clips_dir, exist_ok=True)
    ffmpeg = _ffmpeg_exe()

    created = 0
    prev_end = 0.0
    for idx, (seg, mark) in enumerate(zip(feats, marks)):
        is_first = idx == 0
        is_last = idx == len(feats) - 1
        if is_first:
            # Session start includes sign-in / role-selection / OTP entry, which the
            # narration never covers (see agent_instructions.txt) — start just before
            # this feature's own screenshot instead, so video and audio stay in sync.
            start = max(0.0, mark - _DEFAULT_LEAD_SECONDS)
        else:
            # This feature spans from the previous cut to its own screenshot moment;
            # the last feature extends to the end so trailing action isn't lost.
            start = prev_end
        end = duration if is_last else mark
        if end <= start:
            # Timestamps out of order (clock skew) — fall back to a short lead-in.
            start = max(0.0, end - _DEFAULT_LEAD_SECONDS)
        clip_len = end - start
        if clip_len < _MIN_CLIP_SECONDS:
            prev_end = end
            continue

        out_path = os.path.join(clips_dir, f"feature-{seg.get('order', idx):02d}.mp4")
        if _slice(ffmpeg, session, start, clip_len, out_path):
            seg["clip"] = out_path
            created += 1
        prev_end = end

    _log.info("[slice] Created %d feature clip(s) from the session recording.", created)
    return created
