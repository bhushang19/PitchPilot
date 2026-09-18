"""Compose the final demo video with MoviePy.

For each talking-script segment the screenshot fills the frame with a subtle
Ken Burns zoom while the segment's narration audio plays over it. Segments are
joined with short crossfades. Optional background music is mixed in well below
the speech.

Targets the MoviePy 2.x API. Title cards are rendered with Pillow so no
ImageMagick install is required.
"""

import os

import numpy as np

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    afx,
    vfx,
)

CROSSFADE = 0.4                   # seconds of crossfade between segments
KEN_BURNS_ZOOM = 0.06             # total zoom growth over a segment
TITLE_BG_COLOR = (17, 17, 27)     # dark indigo backdrop for title cards
WORDS_PER_SECOND = 2.6            # used only to estimate dry-run placeholder length


def _cover_resize(clip, w, h):
    """Scale a clip so it fully covers a w x h frame (may overflow one axis)."""
    iw, ih = clip.size
    scale = max(w / iw, h / ih)
    return clip.resized(scale)


def _ken_burns(clip, duration):
    """Apply a subtle centered zoom over the clip's duration."""
    if not duration:
        return clip
    return clip.resized(lambda t: 1 + KEN_BURNS_ZOOM * (t / duration))


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


def _background_clip(seg, duration, w, h):
    """Screenshot background with Ken Burns, or a title card if no screenshot."""
    shot = seg.get("screenshot")
    if shot and os.path.isfile(shot):
        base = ImageClip(shot).with_duration(duration)
        base = _cover_resize(base, w, h)
        base = _ken_burns(base, duration).with_position("center")
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


def _add_background_music(video, music_path, volume):
    if not music_path or not os.path.isfile(music_path):
        return video
    music = AudioFileClip(music_path).with_effects(
        [
            afx.AudioLoop(duration=video.duration),
            afx.MultiplyVolume(volume),
            afx.AudioFadeIn(1.0),
            afx.AudioFadeOut(1.5),
        ]
    )
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
