"""Generate an organic, spoken talking script from parsed demo segments.

Uses the project's Azure OpenAI deployment to rewrite the presenter-oriented
narration ("What to say" notes) into natural, first-person avatar speech with
smooth transitions between features, plus a short intro and outro. The result is
saved to disk as `talking-script.json` (machine-readable, drives synthesis) and
`talking-script.md` (human-readable review copy).
"""

import json
import os

from openai import AzureOpenAI

from core.personas import STORYTELLING_FRAMEWORK

_SYSTEM_PROMPT = (
    "You are a scriptwriter for a professional product demo video. You turn terse presenter notes into a warm, confident, "
    "spoken-word script. Write the way a skilled presenter actually speaks: "
    "first person plural ('let's', 'you'll see'), short sentences, natural "
    "connective transitions between sections, no bullet points, no markdown, no "
    "stage directions, and no reading of URLs or file names aloud. Keep each "
    "feature's narration roughly the length of the source note (about 40-90 "
    "words). Do not invent features that are not described."
)


def _build_system_prompt(persona=None):
    """Compose the system prompt: base voice + storytelling scaffold + persona lens."""
    parts = [_SYSTEM_PROMPT, "", STORYTELLING_FRAMEWORK]
    persona_instructions = ((persona or {}).get("instructions") or "").strip()
    if persona_instructions:
        parts.append("")
        parts.append(f"TARGET AUDIENCE: {persona.get('name', '')}.")
        parts.append(
            "Tune the narration for this audience — emphasise what they care about and "
            "frame every benefit through their priorities:"
        )
        parts.append(persona_instructions)
    return "\n".join(parts)


def _build_user_prompt(parsed):
    features = []
    for seg in parsed.segments:
        features.append(
            {
                "order": seg.order,
                "beat": seg.beat,
                "name": seg.name,
                "hook": seg.hook,
                "presenter_note": seg.say_source,
                "on_screen_steps": seg.steps,
                "why_it_matters": seg.why,
                "transition_hint": seg.transition,
            }
        )

    payload = {
        "video_title": parsed.title,
        "overview": parsed.overview,
        "closing": parsed.closing,
        "features": features,
    }

    return (
        "Write the spoken narration for this demo video. Return ONLY a JSON object "
        "with this exact shape:\n"
        "{\n"
        '  "intro": "<20-40 word spoken opening that welcomes the viewer and frames the demo>",\n'
        '  "segments": [ {"order": <int>, "spoken_text": "<spoken narration for that feature>"} ],\n'
        '  "outro": "<20-40 word spoken closing / call to action>"\n'
        "}\n"
        "Include exactly one segment entry per input feature, preserving the order "
        "values. Make the narration flow as one continuous talk: the first feature "
        "should follow naturally from the intro, each subsequent feature should open "
        "with a brief transition from the previous one, and the outro should wrap up. "
        "Here is the source material as JSON:\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _strip_code_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _call_model(config, parsed, persona=None):
    client = AzureOpenAI(
        api_key=config.openai_api_key,
        azure_endpoint=config.openai_endpoint,
        api_version=config.openai_api_version,
    )
    messages = [
        {"role": "system", "content": _build_system_prompt(persona)},
        {"role": "user", "content": _build_user_prompt(parsed)},
    ]

    kwargs = {"model": config.openai_deployment, "messages": messages, "temperature": 0.6}
    try:
        resp = client.chat.completions.create(
            response_format={"type": "json_object"}, **kwargs
        )
    except Exception:
        # Older deployments may not support response_format; retry without it.
        resp = client.chat.completions.create(**kwargs)

    content = resp.choices[0].message.content or ""
    return json.loads(_strip_code_fences(content))


def generate_talking_script(config, parsed, persona=None):
    """Return a talking-script dict combining AI narration with segment metadata."""
    ai = _call_model(config, parsed, persona)

    spoken_by_order = {
        int(s["order"]): (s.get("spoken_text") or "").strip()
        for s in ai.get("segments", [])
        if "order" in s
    }

    video_segments = []
    intro_text = (ai.get("intro") or "").strip()
    if intro_text:
        video_segments.append(
            {
                "order": 0,
                "kind": "intro",
                "beat": "",
                "name": parsed.title,
                "screenshot": parsed.segments[0].screenshot if parsed.segments else None,
                "spoken_text": intro_text,
            }
        )

    for seg in parsed.segments:
        spoken = spoken_by_order.get(seg.order) or seg.say_source
        seg.spoken_text = spoken
        video_segments.append(
            {
                "order": seg.order,
                "kind": "feature",
                "beat": seg.beat,
                "name": seg.name,
                "screenshot": seg.screenshot,
                "spoken_text": spoken,
            }
        )

    outro_text = (ai.get("outro") or "").strip()
    if outro_text:
        video_segments.append(
            {
                "order": len(parsed.segments) + 1,
                "kind": "outro",
                "beat": "",
                "name": "Thank you",
                "screenshot": None,
                "spoken_text": outro_text,
            }
        )

    return {
        "title": parsed.title,
        "source": parsed.source_path,
        "voice": config.narration_voice,
        "segments": video_segments,
    }


def save_talking_script(script, out_dir):
    """Write talking-script.json and a readable talking-script.md; return their paths."""
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "talking-script.json")
    md_path = os.path.join(out_dir, "talking-script.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    lines = [f"# {script['title']} — Talking Script", ""]
    for seg in script["segments"]:
        if seg["kind"] == "intro":
            lines.append("## Intro")
        elif seg["kind"] == "outro":
            lines.append("## Outro")
        else:
            label = seg["name"] or f"Segment {seg['order']}"
            beat = f" ({seg['beat']})" if seg["beat"] else ""
            lines.append(f"## {seg['order']}. {label}{beat}")
        if seg.get("screenshot"):
            lines.append(f"*Screenshot: {os.path.basename(seg['screenshot'])}*")
        lines.append("")
        lines.append(seg["spoken_text"])
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return json_path, md_path
