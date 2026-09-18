"""Parse a narrator demo script (Markdown or HTML) into ordered video segments.

Markdown (`demo-script.md`) is the canonical source: it is parsed with the same
`parse_script` used by the HTML renderer, so the structure stays in lock-step.
HTML input (`demo-script.html` / `latest.html`) is supported as a best-effort
fallback by reading the rendered feature blocks.

Each feature becomes one `Segment`; each segment maps to one avatar clip shown
over its screenshot in the final video.
"""

import base64
import hashlib
import mimetypes
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from core.render_html import parse_script, _resolve_shot


@dataclass
class Segment:
    order: int
    beat: str
    name: str
    url: str = ""
    screenshot: Optional[str] = None  # absolute path, or None if unresolved
    hook: str = ""
    say_source: str = ""              # presenter narration from the script
    steps: List[str] = field(default_factory=list)
    why: str = ""
    transition: str = ""
    spoken_text: str = ""             # filled in later by script_generator


@dataclass
class ParsedScript:
    title: str
    overview: str
    closing: str
    segments: List[Segment]
    source_path: str
    screenshots_dir: str


_TEMP_SHOT_DIR = None


def _decode_data_uri(uri):
    """Decode a base64 data: URI (e.g. from a standalone latest.html) to a temp file."""
    m = re.match(r"data:(?P<mime>[^;,]*);base64,(?P<data>.*)$", uri.strip(), re.DOTALL)
    if not m:
        return None
    try:
        raw = base64.b64decode(m.group("data"))
    except (ValueError, TypeError):
        return None
    ext = mimetypes.guess_extension(m.group("mime") or "image/png") or ".png"
    global _TEMP_SHOT_DIR
    if _TEMP_SHOT_DIR is None:
        _TEMP_SHOT_DIR = tempfile.mkdtemp(prefix="avatar_shots_")
    path = os.path.join(_TEMP_SHOT_DIR, hashlib.sha1(raw).hexdigest()[:16] + ext)
    if not os.path.isfile(path):
        with open(path, "wb") as f:
            f.write(raw)
    return path


def _abs_shot(shot_field, screenshots_dir):
    """Resolve a screenshot reference to an absolute file path, or None."""
    if shot_field and shot_field.strip().startswith("data:"):
        return _decode_data_uri(shot_field)
    rel = _resolve_shot(shot_field, screenshots_dir)
    if not rel:
        return None
    abs_path = os.path.join(os.path.dirname(screenshots_dir.rstrip(os.sep)), rel)
    return abs_path if os.path.isfile(abs_path) else None


def _parse_markdown(path):
    with open(path, "r", encoding="utf-8") as f:
        doc = parse_script(f.read())

    src_dir = os.path.dirname(os.path.abspath(path))
    screenshots_dir = os.path.join(src_dir, "screenshots")

    segments = []
    order = 0
    for beat in doc["beats"]:
        for feat in beat["features"]:
            order += 1
            segments.append(
                Segment(
                    order=order,
                    beat=beat["title"],
                    name=feat.get("name", "").strip(),
                    url=feat.get("url", "").strip(),
                    screenshot=_abs_shot(feat.get("shot", ""), screenshots_dir),
                    hook=feat.get("hook", "").strip(),
                    say_source=feat.get("say", "").strip(),
                    steps=[s.strip() for s in feat.get("steps", []) if s.strip()],
                    why=feat.get("why", "").strip(),
                    transition=feat.get("transition", "").strip(),
                )
            )

    return ParsedScript(
        title=doc.get("title", "Presenter Demo"),
        overview=" ".join(doc.get("overview", [])).strip(),
        closing=" ".join(doc.get("closing", [])).strip(),
        segments=segments,
        source_path=os.path.abspath(path),
        screenshots_dir=screenshots_dir,
    )


def _text(node):
    return node.get_text(" ", strip=True) if node else ""


def _follow_redirect(path, soup):
    """If the HTML is a meta-refresh stub (e.g. latest.html), return the target path."""
    meta = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"})
    if not meta:
        return None
    content = meta.get("content", "")
    m = re.search(r"url\s*=\s*(.+)$", content, re.IGNORECASE)
    if not m:
        return None
    target = m.group(1).strip().strip("'\"")
    target_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(path)), target))
    return target_path if os.path.isfile(target_path) else None


def _parse_html(path):
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:  # pragma: no cover - guidance path
        raise ImportError(
            "Parsing HTML input requires beautifulsoup4. Install it with "
            "`pip install beautifulsoup4`, or pass the demo-script.md instead."
        ) from e

    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # latest.html is a redirect stub with no content; follow it to the real render.
    redirect = _follow_redirect(path, soup)
    if redirect:
        return parse_input(redirect)

    src_dir = os.path.dirname(os.path.abspath(path))
    screenshots_dir = os.path.join(src_dir, "screenshots")

    title_el = soup.find("h1")
    title = _text(title_el) or "Presenter Demo"

    overview_el = soup.find(id="overview")
    overview = " ".join(_text(p) for p in overview_el.find_all("p")) if overview_el else ""
    closing_el = soup.find(id="closing")
    closing = " ".join(_text(p) for p in closing_el.find_all("p")) if closing_el else ""

    segments = []
    order = 0
    for beat_section in soup.select("section.beat"):
        heading = beat_section.find("h2")
        beat_title = _text(heading)
        badge = heading.find(class_="beat-badge") if heading else None
        if badge:
            beat_title = beat_title.replace(_text(badge), "", 1).strip()

        for feat in beat_section.select("details.feature"):
            order += 1
            name = _text(feat.find(class_="feature-name"))
            open_link = feat.find(class_="open-page")
            url = open_link.get("href", "").strip() if open_link else ""

            img = feat.select_one(".shot img")
            shot_ref = img.get("src", "") if img else ""

            hook = _text(feat.find(class_="hook"))
            say_el = feat.find(class_="say")
            say = _text(say_el.find("p")) if say_el and say_el.find("p") else ""
            steps = [_text(li) for li in feat.select(".steps li")]
            why_el = feat.find(class_="why")
            why = ""
            if why_el:
                spans = why_el.find_all("span")
                why = _text(spans[-1]) if spans else _text(why_el)

            segments.append(
                Segment(
                    order=order,
                    beat=beat_title,
                    name=name,
                    url=url,
                    screenshot=_abs_shot(shot_ref, screenshots_dir),
                    hook=hook,
                    say_source=say,
                    steps=[s for s in steps if s],
                    why=why,
                )
            )

    return ParsedScript(
        title=title,
        overview=overview,
        closing=closing,
        segments=segments,
        source_path=os.path.abspath(path),
        screenshots_dir=screenshots_dir,
    )


def parse_input(path):
    """Parse a Markdown or HTML demo script into a ParsedScript."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext in (".md", ".markdown", ".txt"):
        return _parse_markdown(path)
    if ext in (".html", ".htm"):
        return _parse_html(path)
    raise ValueError(f"Unsupported input type '{ext}'. Provide a .md or .html file.")
