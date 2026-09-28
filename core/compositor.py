"""Compose the final demo video with MoviePy.

Each segment shows its recorded feature clip (or a static screenshot when no clip
exists) while the segment's narration audio plays over it. Segments are joined with
short crossfades. Optional background music is looped underneath and ducked below the
narration.

Targets the MoviePy 2.x API. Title cards are rendered with Pillow so no
ImageMagick install is required.
"""

import os

import logging

import numpy as np

_log = logging.getLogger(__name__)

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
    vfx,
)

CROSSFADE = 0.4                   # seconds of crossfade between segments
TITLE_BG_COLOR = (17, 17, 27)     # dark indigo backdrop for title cards
WORDS_PER_SECOND = 2.6            # used only to estimate dry-run placeholder length
MUSIC_DUCK = 0.6                  # how far music dips under full-volume narration


def _cover_resize(clip, w, h):
    """Scale a clip so it fully covers a w x h frame (may overflow one axis)."""
    iw, ih = clip.size
    scale = max(w / iw, h / ih)
    return clip.resized(scale)


def _title_card_array(text, w, h):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (w, h), TITLE_BG_COLOR)
    draw = ImageDraw.Draw(img)

    font = None
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, size=int(h * 0.08))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Word-wrap to ~80% of the frame width.
    max_width = int(w * 0.8)
    words = (text or "").split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if not lines:
        lines = [""]

    line_heights = [draw.textbbox((0, 0), ln, font=font)[3] for ln in lines]
    gap = int(h * 0.02)
    total_h = sum(line_heights) + gap * (len(lines) - 1)
    y = (h - total_h) // 2
    for ln, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), ln, font=font)
        x = (w - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), ln, fill=(235, 235, 245), font=font)
        y += lh + gap

    return np.array(img)


def _video_background(clip_path, duration, w, h):
    """Real feature footage sized to the frame, reconciled to the narration length.

    Longer footage is trimmed; shorter footage holds on its last frame so the
    narration is always heard in full over live action.
    """
    base = VideoFileClip(clip_path)
    if base.audio is not None:
        base = base.without_audio()
    base = _cover_resize(base, w, h)
    if base.duration >= duration:
        base = base.subclipped(0, duration)
    elif duration - base.duration > 0.05:
        pad = duration - base.duration
        last = base.to_ImageClip(t=max(0.0, base.duration - 0.05)).with_duration(pad)
        base = concatenate_videoclips([base, last])
    return CompositeVideoClip(
        [base.with_position("center")], size=(w, h)
    ).with_duration(duration)


def _background_clip(seg, duration, w, h):
    """Feature video clip if available, else a static screenshot, else a title card."""
    clip_path = seg.get("clip")
    if clip_path and os.path.isfile(clip_path):
        try:
            return _video_background(clip_path, duration, w, h)
        except Exception as exc:  # noqa: BLE001 - fall back to the still on any decode error
            _log.warning(
                "[compose] Clip failed (%s): %s; using screenshot instead.",
                os.path.basename(clip_path),
                exc,
            )

    shot = seg.get("screenshot")
    if shot and os.path.isfile(shot):
        base = ImageClip(shot).with_duration(duration)
        base = _cover_resize(base, w, h).with_position("center")
        return CompositeVideoClip([base], size=(w, h)).with_duration(duration)

    card = ImageClip(_title_card_array(seg.get("name", ""), w, h)).with_duration(duration)
    return card


def _estimated_duration(seg):
    """Dry-run stand-in length when no narration audio has been synthesized."""
    words = len((seg.get("spoken_text") or "").split())
    return max(2.5, words / WORDS_PER_SECOND)


def _segment_clip(seg, clip_path, w, h, dry_run):
    if dry_run or not clip_path or not os.path.isfile(clip_path):
        duration = _estimated_duration(seg)
        audio = None
    else:
        audio = AudioFileClip(clip_path)
        duration = audio.duration

    background = _background_clip(seg, duration, w, h)
    composite = CompositeVideoClip([background], size=(w, h)).with_duration(duration)
    if audio is not None:
        composite = composite.with_audio(audio)
    return composite


def _concat_crossfade(clips, w, h):
    """Lay clips on a timeline overlapping by CROSSFADE with a dissolve."""
    if len(clips) == 1:
        return clips[0]
    positioned = [clips[0]]
    t = clips[0].duration
    for clip in clips[1:]:
        start = max(0.0, t - CROSSFADE)
        positioned.append(
            clip.with_start(start).with_effects([vfx.CrossFadeIn(CROSSFADE)])
        )
        t = start + clip.duration
    return CompositeVideoClip(positioned, size=(w, h)).with_duration(t)


def _speech_envelope(audio, sr=4000, smooth_s=0.15):
    """Return (times, gain[0..1]) tracking how loud the narration is over time."""
    samples = audio.to_soundarray(fps=sr)
    amp = np.abs(samples).max(axis=1) if samples.ndim == 2 else np.abs(samples)
    win = max(1, int(smooth_s * sr))
    smooth = np.convolve(amp, np.ones(win) / win, mode="same")
    ref = np.percentile(smooth, 90) or float(smooth.max() or 1.0)
    env = np.clip(smooth / (ref or 1.0), 0.0, 1.0)
    step = max(1, int(0.02 * sr))  # ~20 ms envelope resolution keeps interp cheap
    times = np.arange(len(env), dtype="float64") / sr
    return times[::step], env[::step]


def _ducking_transform(env_times, env_gain, ceiling, duck):
    """MoviePy audio transform: scale music by the ceiling, dipping it under speech."""
    def transform(get_frame, t):
        frame = get_frame(t)
        speech = np.interp(t, env_times, env_gain)
        factor = np.asarray(ceiling * (1.0 - duck * speech))
        if getattr(frame, "ndim", 1) == 2:
            return frame * factor.reshape(-1, 1)
        return frame * factor
    return transform


def _add_background_music(video, music_path, volume):
    if not music_path or not os.path.isfile(music_path):
        return video
    music = AudioFileClip(music_path).with_effects([afx.AudioLoop(duration=video.duration)])
    if video.audio is not None:
        # Side-chain style ducking: music sits at `volume` in the gaps and dips under
        # the narration so speech always stays clearly on top.
        env_times, env_gain = _speech_envelope(video.audio)
        music = music.transform(_ducking_transform(env_times, env_gain, volume, MUSIC_DUCK))
    else:
        music = music.with_effects([afx.MultiplyVolume(volume)])
    music = music.with_effects([afx.AudioFadeIn(1.0), afx.AudioFadeOut(1.5)])
    mixed = CompositeAudioClip([video.audio, music]) if video.audio is not None else music
    return video.with_audio(mixed)


def build_video(config, rendered_segments, out_path, music_path=None, dry_run=False):
    """Compose segments into out_path. rendered_segments = list of (seg, clip_path)."""
    w, h = config.resolution
    clips = [_segment_clip(seg, clip_path, w, h, dry_run)
             for seg, clip_path in rendered_segments]
    if not clips:
        raise ValueError("No segments to compose.")

    final = _concat_crossfade(clips, w, h)

    if config.enable_bg_music:
        final = _add_background_music(final, music_path, config.bg_music_volume)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    final.write_videofile(
        out_path,
        fps=config.fps,
        codec="libx264",
        audio_codec="aac",
        audio=final.audio is not None,
        threads=4,
    )
    return out_path
