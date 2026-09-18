"""PitchPilot — one entry point for the demo-to-video pipeline.

Stages:
  1. Explore the app          -> demo-script.md + screenshots
  2. Write the talking script -> talking-script.json / .md   (Azure OpenAI)
  3. Render the narrated video -> demo-video.mp4              (--video)

Usage:
    python pitchpilot.py                       # stages 1 + 2 (transcript only)
    python pitchpilot.py --video               # stages 1 + 2 + 3
    python pitchpilot.py --from-script PATH --video   # stage 3 only (resume)
    python pitchpilot.py --video --dry-run     # silent preview (no billable TTS)
    python pitchpilot.py --format html         # HTML demo script instead of md
"""

import argparse
import asyncio
import os
import sys
import traceback
from getpass import getpass

from dotenv import load_dotenv

from core import explorer, video
from core.config import Config
from core.input_parser import parse_input
from core.render_html import render_html
from core.script_generator import generate_talking_script, save_talking_script

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SPEC_SIZE_WARN_CHARS = 40_000


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="pitchpilot", description="Demo-to-video pipeline.")
    p.add_argument("--video", action="store_true",
                   help="Also synthesize narration and render demo-video.mp4.")
    p.add_argument("--from-script", dest="from_script", metavar="PATH",
                   help="Render the video from an existing talking-script.json (skips stages 1-2).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compose a silent preview without calling Azure Text-to-Speech.")
    p.add_argument("--format", choices=("md", "html"), default="md",
                   help="Presenter demo-script output format (default: md).")
    return p.parse_args(argv[1:])


def _prompt_inputs():
    base_url = input("Base URL of the app: ").strip()
    if not base_url:
        print("Base URL is required. Aborting.")
        sys.exit(1)

    print("Sign-in credentials (leave blank if the app needs no login):")
    username = input("  Username / email (optional): ").strip()
    password = getpass("  Password (optional, hidden): ")
    mfa_code = input("  MFA / OTP code (optional): ").strip()

    spec_path = input("Path to spec document (.md or .txt, optional): ").strip().strip('"')
    spec_text = ""
    if spec_path:
        if not os.path.isfile(spec_path):
            print(f"Spec document not found: {spec_path}")
            sys.exit(1)
        with open(spec_path, "r", encoding="utf-8") as f:
            spec_text = f.read()
        if len(spec_text) > SPEC_SIZE_WARN_CHARS:
            print(f"[warn] Spec document is {len(spec_text)} chars — this may strain the "
                  f"model context window. Continuing anyway.")
    return base_url, username, password, mfa_code, spec_text


def _render_html_outputs(script_path, app_slug, fmt):
    """Optional demo-script.html + always a standalone shareable latest.html."""
    run_dir = os.path.dirname(script_path)
    if fmt == "html":
        html_path = os.path.join(run_dir, "demo-script.html")
        try:
            render_html(script_path, html_path)
            print(f"Polished HTML version: {html_path}")
        except Exception as e:
            print(f"[warn] HTML render failed: {e}")
    try:
        latest_path = os.path.join(_OUTPUT_DIR, app_slug, "latest.html")
        render_html(script_path, latest_path, embed=True)
        print(f"Shareable standalone: {latest_path}")
    except Exception as e:
        print(f"[warn] Standalone latest.html render failed: {e}")


def main():
    print("\n=== PitchPilot ===\n")
    args = _parse_args(sys.argv)
    config = Config.load()

    # Stage 3 only: render straight from an existing talking script.
    if args.from_script:
        if not args.dry_run:
            missing = config.missing_for_narration()
            if missing:
                print(f"Error: missing env vars for narration: {', '.join(missing)}")
                print("Add them to .env, or re-run with --dry-run for a silent preview.")
                return
        video.render_from_script(config, args.from_script, args.dry_run)
        return

    missing_script = config.missing_for_script()
    if missing_script:
        print(f"Error: missing env vars for exploration/script: {', '.join(missing_script)}")
        return
    if args.video and not args.dry_run:
        missing_narration = config.missing_for_narration()
        if missing_narration:
            print(f"Error: missing env vars for narration: {', '.join(missing_narration)}")
            print("Add them to .env, or re-run with --dry-run for a silent preview.")
            return

    base_url, username, password, mfa_code, spec_text = _prompt_inputs()

    try:
        # Stage 1 — explore the app.
        run_dir, app_slug, script_path = asyncio.run(
            explorer.explore(config, base_url, spec_text, username, password, mfa_code)
        )
        if not os.path.isfile(script_path):
            print(f"\n[warn] Expected {script_path} was not found. Check agent output above.")
            return
        print(f"\nDemo script written to: {script_path}")
        _render_html_outputs(script_path, app_slug, args.format)

        # Stage 2 — write the talking script.
        parsed = parse_input(script_path)
        if not parsed.segments:
            print("No feature segments found in the demo script. Nothing to narrate.")
            return
        print(f"\nGenerating talking script for {len(parsed.segments)} segment(s)...")
        script = generate_talking_script(config, parsed)
        json_path, md_path = save_talking_script(script, run_dir)
        print(f"  Talking script saved: {json_path}")
        print(f"  Readable copy:        {md_path}")

        # Stage 3 — render the video (optional).
        if args.video:
            video.render_video(config, script["segments"], run_dir, app_slug, args.dry_run)
        else:
            print("\nTalking transcript ready. To make the video later, run:")
            print(f'  python pitchpilot.py --from-script "{json_path}" --video')
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
