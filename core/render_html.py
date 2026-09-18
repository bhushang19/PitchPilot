"""Standalone Markdown -> polished HTML renderer for presenter demo scripts.

Parses the structured demo-script markdown (title, overview, story beats,
feature panels with "What to say / click / why", Q&A, closing) into a data
model, then renders a clean, professional, self-contained HTML file designed
to help a presenter run a live walkthrough.

Usage:
  Programmatic:
      from render_html import render_html
      render_html("output/demo-script.md", "output/demo-script.html")

  CLI:
      python render_html.py <markdown_path> [html_path]
"""

import html as html_mod
import base64
import mimetypes
import os
import re
import sys


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _inline(text):
    """Render inline markdown (bold, italic, code, links) in a short fragment."""
    text = text.strip()
    # links [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )
    # bare urls -> links
    def _link_bare(m):
        return f'<a href="{m.group(0)}" target="_blank" rel="noopener">{m.group(0)}</a>'
    text = re.sub(r'(?<!["\'>=])(https?://[^\s<)]+)', _link_bare, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def parse_script(md_text):
    """Parse the demo-script markdown into a structured dict."""
    lines = md_text.splitlines()

    doc = {
        "title": "Presenter Demo Script",
        "overview": [],
        "agenda": [],         # "Demo at a glance" bullets
        "beats": [],
        "notes": [],          # special ### sections (Not covered / Known issues)
        "qa": [],
        "closing": [],
    }

    i = 0
    section = None            # overview / features / qa / closing
    current_beat = None
    current_feature = None
    current_field = None      # active **Field:** being appended to

    def flush_feature():
        nonlocal current_feature
        if current_feature and current_beat is not None:
            current_beat["features"].append(current_feature)
        current_feature = None

    def flush_beat():
        nonlocal current_beat
        flush_feature()
        if current_beat is not None:
            doc["beats"].append(current_beat)
        current_beat = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Title
        m = re.match(r"^#\s+(.*)$", line)
        if m:
            doc["title"] = m.group(1).strip()
            i += 1
            continue

        # ## Section
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            flush_beat()
            heading = m.group(1).strip().lower()
            if "glance" in heading or "agenda" in heading:
                section = "agenda"
            elif "overview" in heading:
                section = "overview"
            elif "question" in heading or "q&a" in heading or "q & a" in heading:
                section = "qa"
            elif "closing" in heading:
                section = "closing"
            else:
                section = "features"
            current_field = None
            i += 1
            continue

        # ### Beat or special note section (within features)
        m = re.match(r"^###\s+(.*)$", line)
        if m and section == "features":
            flush_beat()
            heading = m.group(1).strip()
            heading_l = heading.lower()
            # Only a few well-known headings are non-beat "note" sections; every
            # other ### under the narration is a story beat (with or without a
            # literal "Beat N:" prefix).
            is_note = (
                "not covered" in heading_l
                or "not in this build" in heading_l
                or "out of scope" in heading_l
                or "known issue" in heading_l
                or "known problem" in heading_l
            )
            if is_note:
                doc["notes"].append({"title": heading, "items": [], "raw": []})
                current_beat = None
            else:
                bm = re.match(r"^beat\s*\d*\s*[:\-]?\s*(.*)$", heading, re.IGNORECASE)
                title = bm.group(1).strip() if bm and bm.group(1).strip() else heading
                num = re.match(r"^beat\s*(\d+)", heading, re.IGNORECASE)
                current_beat = {
                    "num": num.group(1) if num else str(len(doc["beats"]) + 1),
                    "title": title,
                    "features": [],
                }
            current_field = None
            i += 1
            continue

        # #### Feature
        m = re.match(r"^####\s+(.*)$", line)
        if m and section == "features" and current_beat is not None:
            flush_feature()
            current_feature = {
                "name": m.group(1).strip(),
                "url": "",
                "shot": "",
                "hook": "",
                "say": "",
                "steps": [],
                "cue": "",
                "why": "",
            }
            current_field = None
            i += 1
            continue

        # Feature fields
        if current_feature is not None:
            fm = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", stripped)
            if fm:
                label = fm.group(1).strip().lower()
                value = fm.group(2).strip()
                if "url" in label:
                    current_feature["url"] = value
                    current_field = None
                elif "screenshot" in label or label == "shot":
                    current_feature["shot"] = value
                    current_field = None
                elif "hook" in label:
                    current_feature["hook"] = value
                    current_field = "hook"
                elif "say" in label:
                    current_feature["say"] = value
                    current_field = "say"
                elif "click" in label or "show" in label:
                    current_field = "steps"
                elif "cue" in label:
                    current_feature["cue"] = value
                    current_field = "cue"
                elif "matter" in label:
                    current_feature["why"] = value
                    current_field = "why"
                else:
                    current_field = None
                i += 1
                continue

            sm = re.match(r"^(?:\d+\.|[-*])\s+(.*)$", stripped)
            if sm and current_field == "steps":
                current_feature["steps"].append(sm.group(1).strip())
                i += 1
                continue

            tm = re.match(r"^\*([^*].*?)\*$", stripped)
            if tm and stripped.startswith("*") and stripped.endswith("*") and "**" not in stripped:
                current_feature["transition"] = tm.group(1).strip()
                i += 1
                continue

            if stripped and current_field in ("hook", "say", "cue", "why"):
                current_feature[current_field] += " " + stripped
                i += 1
                continue

        # Special note sections: collect bullets / raw
        if section == "features" and current_beat is None and doc["notes"]:
            note = doc["notes"][-1]
            sm = re.match(r"^[-*]\s+(.*)$", stripped)
            if sm:
                note["items"].append(sm.group(1).strip())
                i += 1
                continue
            if stripped:
                note["raw"].append(stripped)
                i += 1
                continue

        # Overview paragraphs
        if section == "overview" and stripped:
            doc["overview"].append(stripped)
            i += 1
            continue

        # Demo at a glance — one bullet per beat
        if section == "agenda" and stripped:
            am = re.match(r"^[-*]\s+(.*)$", stripped)
            if am:
                doc["agenda"].append(am.group(1).strip())
            i += 1
            continue

        # Q&A
        if section == "qa":
            qm = re.match(r"^\*\*(Q\d+[.:]?\s*.*?)\*\*\s*(.*)$", stripped)
            if qm:
                doc["qa"].append({"q": qm.group(1).strip(), "a": qm.group(2).strip()})
                i += 1
                continue
            if stripped and doc["qa"]:
                doc["qa"][-1]["a"] += (" " if doc["qa"][-1]["a"] else "") + stripped
                i += 1
                continue

        # Closing
        if section == "closing" and stripped:
            doc["closing"].append(stripped)
            i += 1
            continue

        i += 1

    flush_beat()
    return doc


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _split_step(step):
    """Split a step into (action, reason) on a spaced em/en-dash separator.

    Returns (step, "") when no separator is present so older scripts still
    render unchanged.
    """
    m = re.match(r"^(.*?)\s+[\u2014\u2013]\s+(.*)$", step)
    if m and m.group(1).strip() and m.group(2).strip():
        return m.group(1).strip(), m.group(2).strip()
    return step, ""


_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _resolve_shot(value, screenshots_dir):
    """Resolve a Screenshot field to a relative <img> src, or None.

    Accepts an exact file name/path or a bare slug, and tolerates the timestamp
    the screenshot tool appends by matching on a slug prefix. Returns a path
    relative to the HTML file (screenshots/<file>).
    """
    if not value or not screenshots_dir:
        return None
    base = os.path.basename(value.strip().strip("`").replace("\\", "/").rstrip("/"))
    if not base:
        return None
    exact = os.path.join(screenshots_dir, base)
    if os.path.isfile(exact):
        return "screenshots/" + base
    stem = os.path.splitext(base)[0]
    slug = re.split(r"-\d{4}-\d{2}-\d{2}", stem)[0] or stem
    try:
        matches = [
            f for f in os.listdir(screenshots_dir)
            if f.lower().startswith(slug.lower()) and f.lower().endswith(_IMG_EXTS)
        ]
    except OSError:
        return None
    if not matches:
        return None
    matches.sort(
        key=lambda f: os.path.getmtime(os.path.join(screenshots_dir, f)), reverse=True
    )
    return "screenshots/" + matches[0]


def _data_uri(rel_shot, screenshots_dir):
    """Turn a resolved 'screenshots/<file>' reference into a base64 data: URI.

    Used for standalone/shareable HTML so the file carries its images inline and
    needs no external screenshots/ folder. Returns None if the file is missing.
    """
    if not rel_shot or not screenshots_dir:
        return None
    abs_path = os.path.join(screenshots_dir, os.path.basename(rel_shot))
    if not os.path.isfile(abs_path):
        return None
    mime, _ = mimetypes.guess_type(abs_path)
    if not mime:
        ext = os.path.splitext(abs_path)[1].lower().lstrip(".") or "png"
        mime = f"image/{ext}"
    with open(abs_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _render_feature(feat, index, screenshots_dir=None, embed=False):
    parts = []
    open_attr = " open" if index == 0 else ""
    parts.append(f'<details class="feature"{open_attr}>')
    parts.append('<summary>')
    parts.append(f'<span class="feature-name">{html_mod.escape(feat["name"])}</span>')
    if feat.get("url"):
        parts.append(
            f'<a class="open-page" href="{html_mod.escape(feat["url"])}" '
            f'target="_blank" rel="noopener" onclick="event.stopPropagation()">Open page &#8599;</a>'
        )
    parts.append('<span class="chevron" aria-hidden="true"></span>')
    parts.append('</summary>')
    parts.append('<div class="feature-body">')

    if feat.get("hook"):
        parts.append(f'<p class="hook">{_inline(feat["hook"])}</p>')

    shot = _resolve_shot(feat.get("shot", ""), screenshots_dir)
    if shot:
        src = shot
        if embed:
            src = _data_uri(shot, screenshots_dir) or shot
        src_attr = html_mod.escape(src)
        parts.append(
            f'<a class="shot" href="{src_attr}" target="_blank" '
            f'rel="noopener" onclick="event.stopPropagation()">'
            f'<img src="{src_attr}" loading="lazy" '
            f'alt="Screenshot of {html_mod.escape(feat["name"])}">'
            f'<span class="shot-hint">Click to enlarge</span></a>'
        )

    if feat.get("say"):
        parts.append('<div class="say"><div class="say-label">Say this</div>')
        parts.append(f'<p>{_inline(feat["say"])}</p></div>')

    if feat.get("steps"):
        parts.append('<div class="steps"><div class="steps-label">Do this on screen</div><ol>')
        for step in feat["steps"]:
            action, reason = _split_step(step)
            if reason:
                parts.append(
                    f'<li><span class="step-action">{_inline(action)}</span>'
                    f'<span class="step-reason">{_inline(reason)}</span></li>'
                )
            else:
                parts.append(f'<li>{_inline(step)}</li>')
        parts.append('</ol></div>')

    if feat.get("cue"):
        parts.append(
            f'<div class="cue"><span class="cue-label">Presenter cue</span>'
            f'<span>{_inline(feat["cue"])}</span></div>'
        )

    if feat.get("why"):
        parts.append(
            f'<div class="why"><span class="why-label">Why it matters</span>'
            f'<span>{_inline(feat["why"])}</span></div>'
        )

    parts.append('</div></details>')

    if feat.get("transition"):
        parts.append(f'<p class="transition">{_inline(feat["transition"])}</p>')

    return "\n".join(parts)


def _render_body(doc, screenshots_dir=None, embed=False):
    out = []

    if doc["overview"]:
        out.append('<section class="card overview" id="overview">')
        out.append('<h2><span class="dot"></span>Overview</h2>')
        for para in doc["overview"]:
            out.append(f'<p>{_inline(para)}</p>')
        out.append('</section>')

    if doc["agenda"]:
        out.append('<section class="card agenda" id="agenda">')
        out.append('<h2><span class="dot"></span>Demo at a glance</h2>')
        out.append('<ol class="agenda-list">')
        for item in doc["agenda"]:
            out.append(f'<li>{_inline(item)}</li>')
        out.append('</ol>')
        out.append('</section>')

    for beat in doc["beats"]:
        out.append(f'<section class="card beat" id="beat-{beat["num"]}">')
        out.append(
            f'<h2><span class="beat-badge">{html_mod.escape(beat["num"])}</span>'
            f'{html_mod.escape(beat["title"])}</h2>'
        )
        for idx, feat in enumerate(beat["features"]):
            out.append(_render_feature(feat, idx, screenshots_dir, embed))
        out.append('</section>')

    for note in doc["notes"]:
        out.append('<section class="card note" id="notes">')
        out.append(f'<h2><span class="dot muted"></span>{html_mod.escape(note["title"])}</h2>')
        if note["items"]:
            out.append('<ul class="note-list">')
            for it in note["items"]:
                out.append(f'<li>{_inline(it)}</li>')
            out.append('</ul>')
        if note["raw"]:
            out.append('<pre class="raw">' + html_mod.escape("\n".join(note["raw"])) + '</pre>')
        out.append('</section>')

    if doc["qa"]:
        out.append('<section class="card qa-section" id="qa">')
        out.append('<h2><span class="dot"></span>Anticipated questions</h2>')
        for qa in doc["qa"]:
            out.append('<details class="qa">')
            out.append(f'<summary>{_inline(qa["q"])}<span class="chevron" aria-hidden="true"></span></summary>')
            out.append(f'<div class="qa-body">{_inline(qa["a"])}</div>')
            out.append('</details>')
        out.append('</section>')

    if doc["closing"]:
        out.append('<section class="card closing" id="closing">')
        out.append('<h2><span class="dot"></span>Closing</h2>')
        for para in doc["closing"]:
            out.append(f'<p>{_inline(para)}</p>')
        out.append('</section>')

    return "\n".join(out)


def _render_nav(doc):
    items = ['<a href="#overview" class="nav-item">Overview</a>']
    if doc["agenda"]:
        items.append('<a href="#agenda" class="nav-item">Demo at a glance</a>')
    for beat in doc["beats"]:
        items.append(
            f'<a href="#beat-{beat["num"]}" class="nav-item">'
            f'<span class="nav-num">{html_mod.escape(beat["num"])}</span>'
            f'<span>{html_mod.escape(beat["title"])}</span></a>'
        )
    if doc["notes"]:
        items.append('<a href="#notes" class="nav-item">Notes</a>')
    if doc["qa"]:
        items.append('<a href="#qa" class="nav-item">Questions</a>')
    if doc["closing"]:
        items.append('<a href="#closing" class="nav-item">Closing</a>')
    return "\n".join(items)


def render_html(md_path, html_path=None, embed=False):
    """Convert a markdown demo script into a polished, self-contained HTML file.

    When embed=True, screenshots are inlined as base64 data URIs so the output
    is a single shareable file that needs no external screenshots/ folder.
    """
    if html_path is None:
        base, _ = os.path.splitext(md_path)
        html_path = base + ".html"

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    doc = parse_script(md_text)
    feature_count = sum(len(b["features"]) for b in doc["beats"])
    screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(md_path)), "screenshots")

    html = PAGE.format(
        title=html_mod.escape(doc["title"]),
        nav=_render_nav(doc),
        body=_render_body(doc, screenshots_dir, embed),
        beat_count=len(doc["beats"]),
        feature_count=feature_count,
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --ink: #0b1220; --body: #334155; --muted: #64748b; --faint: #94a3b8;
    --line: #e6eaf0; --line-soft: #eef2f7; --bg: #f5f7fb; --panel: #ffffff;
    --brand: #4f46e5; --brand-dark: #4338ca; --brand-soft: #eef2ff;
    --say-bg: #f6f8ff; --say-bar: #4f46e5;
    --ok: #0e9488; --ok-soft: #f0fdfa;
    --shadow: 0 1px 2px rgba(16,24,40,.04), 0 12px 32px -16px rgba(16,24,40,.18);
    --radius: 16px;
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{ margin: 0; background: var(--bg); color: var(--body);
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    font-size: 16px; line-height: 1.65; -webkit-font-smoothing: antialiased; }}
  h1, h2, h3 {{ color: var(--ink); }}
  a {{ color: var(--brand); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{ background: #f1f5f9; padding: 1px 6px; border-radius: 5px; font-size: 90%; }}

  .layout {{ display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 32px;
    max-width: 1180px; margin: 0 auto; padding: 32px 28px 96px; }}

  aside {{ position: sticky; top: 24px; align-self: start; height: fit-content; }}
  .brandbar {{ background: linear-gradient(135deg, #4f46e5, #6366f1 55%, #7c3aed);
    color: #fff; border-radius: var(--radius); padding: 22px 20px; margin-bottom: 16px;
    box-shadow: var(--shadow); }}
  .brandbar .kicker {{ font-size: 11px; letter-spacing: .16em; text-transform: uppercase;
    color: #c7d2fe; margin-bottom: 8px; }}
  .brandbar h1 {{ color: #fff; font-size: 19px; line-height: 1.3; margin: 0 0 14px; }}
  .brandbar .stats {{ display: flex; gap: 18px; font-size: 12px; color: #dbe1ff; }}
  .brandbar .stats b {{ display: block; color: #fff; font-size: 18px; line-height: 1; margin-bottom: 2px; }}
  nav {{ background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 10px; box-shadow: var(--shadow); }}
  .nav-item {{ display: flex; align-items: center; gap: 10px; padding: 9px 11px;
    border-radius: 10px; color: var(--body); font-size: 14px; font-weight: 500; line-height: 1.35; }}
  .nav-item:hover {{ background: var(--brand-soft); color: var(--brand-dark); text-decoration: none; }}
  .nav-item.active {{ background: var(--brand-soft); color: var(--brand-dark); }}
  .nav-num {{ flex: none; width: 22px; height: 22px; border-radius: 7px; background: var(--brand-soft);
    color: var(--brand-dark); font-size: 12px; font-weight: 700; display: grid; place-items: center; }}
  .nav-item.active .nav-num {{ background: var(--brand); color: #fff; }}

  main {{ min-width: 0; }}
  .toolbar {{ display: flex; gap: 8px; justify-content: flex-end; margin-bottom: 16px; }}
  .toolbar button {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 8px 14px; font-size: 13px; font-weight: 600; color: var(--body); cursor: pointer;
    box-shadow: var(--shadow); }}
  .toolbar button:hover {{ color: var(--brand-dark); border-color: var(--brand); }}

  .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 26px 28px; margin-bottom: 20px; box-shadow: var(--shadow); scroll-margin-top: 20px; }}
  .card h2 {{ display: flex; align-items: center; gap: 12px; margin: 0 0 14px; font-size: 20px; }}
  .card.overview p, .card.closing p {{ margin: 0 0 12px; color: var(--body); }}
  .card.overview p:last-child, .card.closing p:last-child {{ margin-bottom: 0; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; background: var(--brand); flex: none; }}
  .dot.muted {{ background: var(--faint); }}
  .beat-badge {{ width: 30px; height: 30px; border-radius: 9px; flex: none;
    background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #fff;
    font-size: 14px; font-weight: 700; display: grid; place-items: center; }}

  details.feature {{ border: 1px solid var(--line); border-radius: 13px; margin: 12px 0 0;
    overflow: hidden; transition: border-color .15s, box-shadow .15s; background: #fff; }}
  details.feature[open] {{ border-color: #d6dbf5; box-shadow: 0 10px 28px -18px rgba(79,70,229,.55); }}
  details.feature > summary {{ list-style: none; cursor: pointer; display: flex; align-items: center;
    gap: 12px; padding: 15px 18px; font-weight: 650; color: var(--ink); }}
  details.feature > summary::-webkit-details-marker {{ display: none; }}
  .feature-name {{ flex: 1; min-width: 0; }}
  .open-page {{ flex: none; font-size: 12.5px; font-weight: 600; color: var(--brand-dark);
    background: var(--brand-soft); padding: 5px 10px; border-radius: 8px; white-space: nowrap; }}
  .open-page:hover {{ background: #e0e7ff; text-decoration: none; }}
  .chevron {{ flex: none; width: 9px; height: 9px; border-right: 2px solid var(--faint);
    border-bottom: 2px solid var(--faint); transform: rotate(45deg); transition: transform .2s; }}
  details[open] > summary .chevron {{ transform: rotate(-135deg); }}
  .feature-body {{ padding: 4px 18px 20px; }}

  .hook {{ margin: 6px 0 12px; color: var(--ink); font-size: 16px; font-weight: 600;
    line-height: 1.5; padding-left: 12px; border-left: 3px solid var(--brand); }}

  .shot {{ display: block; position: relative; margin: 6px 0 16px; border: 1px solid var(--line);
    border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); line-height: 0; }}
  .shot img {{ width: 100%; height: auto; display: block; max-height: 360px;
    object-fit: cover; object-position: top left; }}
  .shot-hint {{ position: absolute; right: 10px; bottom: 10px; background: rgba(11,18,32,.78);
    color: #fff; font-size: 11px; font-weight: 600; letter-spacing: .04em; padding: 4px 9px;
    border-radius: 7px; line-height: 1.2; opacity: 0; transition: opacity .15s; }}
  .shot:hover {{ border-color: #d6dbf5; }}
  .shot:hover .shot-hint {{ opacity: 1; }}

  .say {{ background: var(--say-bg); border-left: 3px solid var(--say-bar); border-radius: 0 10px 10px 0;
    padding: 12px 16px; margin: 6px 0 16px; }}
  .say-label {{ font-size: 11px; letter-spacing: .12em; text-transform: uppercase; font-weight: 700;
    color: var(--brand-dark); margin-bottom: 4px; }}
  .say p {{ margin: 0; color: var(--ink); font-size: 16.5px; line-height: 1.6; }}

  .steps-label, .why-label {{ font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
    font-weight: 700; color: var(--muted); }}
  .steps {{ margin: 0 0 16px; }}
  .steps ol {{ list-style: none; counter-reset: step; margin: 8px 0 0; padding: 0; }}
  .steps li {{ counter-increment: step; position: relative; padding: 3px 0 3px 34px; margin: 6px 0;
    color: var(--body); }}
  .steps li::before {{ content: counter(step); position: absolute; left: 0; top: 2px;
    width: 23px; height: 23px; border-radius: 7px; background: var(--brand-soft);
    color: var(--brand-dark); font-size: 12px; font-weight: 700; display: grid; place-items: center; }}
  .step-action {{ color: var(--ink); font-weight: 600; }}
  .step-reason {{ display: block; color: var(--muted); font-size: 14.5px; line-height: 1.5;
    margin-top: 1px; }}

  .cue {{ display: flex; gap: 10px; align-items: baseline; background: #fffbeb;
    border: 1px solid #fde68a; border-radius: 10px; padding: 11px 14px; margin: 0 0 16px; }}
  .cue-label {{ flex: none; font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
    font-weight: 700; color: #b45309; }}

  .agenda-list {{ margin: 4px 0 0; padding: 0; list-style: none; counter-reset: agenda; }}
  .agenda-list li {{ counter-increment: agenda; position: relative; padding: 8px 0 8px 38px;
    margin: 2px 0; color: var(--body); border-top: 1px solid var(--line-soft); }}
  .agenda-list li:first-child {{ border-top: none; }}
  .agenda-list li::before {{ content: counter(agenda); position: absolute; left: 0; top: 8px;
    width: 26px; height: 26px; border-radius: 8px; background: var(--brand-soft);
    color: var(--brand-dark); font-size: 12.5px; font-weight: 700; display: grid; place-items: center; }}

  .why {{ display: flex; gap: 10px; align-items: baseline; background: var(--ok-soft);
    border: 1px solid #cffafe; border-radius: 10px; padding: 11px 14px; }}
  .why-label {{ flex: none; color: var(--ok); }}

  .transition {{ margin: 14px 4px 2px; color: var(--muted); font-style: italic; font-size: 14.5px;
    padding-left: 14px; border-left: 3px solid var(--line); }}

  .note-list {{ margin: 0; padding-left: 20px; }}
  .note-list li {{ margin: 6px 0; }}
  pre.raw {{ background: #0b1220; color: #cbd5e1; padding: 14px 16px; border-radius: 10px;
    overflow-x: auto; font-size: 12px; line-height: 1.5; white-space: pre-wrap; }}

  details.qa {{ border-top: 1px solid var(--line-soft); }}
  details.qa:first-of-type {{ border-top: none; }}
  details.qa > summary {{ list-style: none; cursor: pointer; display: flex; align-items: center;
    justify-content: space-between; gap: 12px; padding: 14px 2px; font-weight: 600; color: var(--ink); }}
  details.qa > summary::-webkit-details-marker {{ display: none; }}
  .qa-body {{ padding: 0 2px 16px; color: var(--body); }}

  @media (max-width: 900px) {{
    .layout {{ grid-template-columns: 1fr; }}
    aside {{ position: static; }}
  }}
  @media print {{
    body {{ background: #fff; font-size: 12pt; }}
    .layout {{ display: block; max-width: none; padding: 0; }}
    aside, .toolbar {{ display: none !important; }}
    .card {{ box-shadow: none; border-color: #dde3ec; break-inside: avoid; }}
    details.feature, details.qa {{ break-inside: avoid; }}
    details > summary {{ pointer-events: none; }}
    .chevron {{ display: none; }}
    details:not([open]) > *:not(summary) {{ display: block !important; }}
    .open-page {{ display: none; }}
    .shot {{ break-inside: avoid; }}
    .shot img {{ max-height: none; object-fit: contain; }}
    .shot-hint {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="layout">
  <aside>
    <div class="brandbar">
      <div class="kicker">Presenter Demo Script</div>
      <h1>{title}</h1>
      <div class="stats">
        <div><b>{beat_count}</b>story beats</div>
        <div><b>{feature_count}</b>features</div>
      </div>
    </div>
    <nav>
      {nav}
    </nav>
  </aside>
  <main>
    <div class="toolbar">
      <button onclick="document.querySelectorAll('details').forEach(d=>d.open=true)">Expand all</button>
      <button onclick="document.querySelectorAll('details').forEach(d=>d.open=false)">Collapse all</button>
      <button onclick="window.print()">Print / Save PDF</button>
    </div>
    {body}
  </main>
</div>
<script>
  const links = [...document.querySelectorAll('.nav-item')];
  const map = new Map(links.map(a => [a.getAttribute('href').slice(1), a]));
  const obs = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        links.forEach(l => l.classList.remove('active'));
        const a = map.get(e.target.id);
        if (a) a.classList.add('active');
      }}
    }});
  }}, {{ rootMargin: '-20% 0px -70% 0px', threshold: 0 }});
  document.querySelectorAll('section[id]').forEach(s => obs.observe(s));
</script>
</body>
</html>
"""


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    embed = any(a in ("--embed", "-e") for a in argv[1:])
    if not args or any(a in ("-h", "--help") for a in argv[1:]):
        print("Usage: python render_html.py <markdown_path> [html_path] [--embed]")
        return 1
    md_path = args[0]
    html_path = args[1] if len(args) > 1 else None
    if not os.path.isfile(md_path):
        print(f"Error: markdown file not found: {md_path}")
        return 1
    written = render_html(md_path, html_path, embed=embed)
    print(f"HTML written to: {written}" + (" (standalone, images embedded)" if embed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
