"""Stage 1 — explore a web app and write a presenter demo script.

Drives Microsoft's Playwright MCP (`@playwright/mcp`) + a filesystem MCP through an
Azure OpenAI agent to log in, explore the app, and produce `demo-script.md` (+ one
screenshot per feature) in a timestamped run folder. The Playwright MCP records the
whole headed session to a `.webm` (via `recordVideo`), which a later stage slices
into per-feature clips for a lively, action-driven demo video.
"""

import asyncio
import datetime
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import time
import warnings
from urllib.parse import urlparse

from agents import (
    Agent,
    Runner,
    OpenAIChatCompletionsModel,
    set_default_openai_client,
    set_tracing_disabled,
)
from agents.mcp import MCPServerStdio
from openai import AsyncAzureOpenAI

warnings.filterwarnings("ignore", category=ResourceWarning)

_log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_OUTPUT_DIR = os.path.join(_REPO_ROOT, "output")
_INSTRUCTIONS_PATH = os.path.join(_HERE, "agent_instructions.txt")

MAX_TURNS = 100

# Session-recording size. Kept at 720p for smooth headed capture; the compositor
# cover-resizes clips up to the final video resolution.
_RECORD_WIDTH = 1280
_RECORD_HEIGHT = 720


def _ensure_playwright_mcp():
    """Install Microsoft's Playwright MCP + its exact Chromium locally.

    Installing `@playwright/mcp` into a local node_modules and running
    `playwright install chromium` from there keeps the browser aligned with the MCP
    server's pinned Playwright by construction. All steps are idempotent.
    """
    node_modules = os.path.join(_REPO_ROOT, "node_modules")
    pkg_json = os.path.join(_REPO_ROOT, "package.json")

    if not os.path.isfile(pkg_json):
        _log.info("[preflight] Creating local package.json...")
        try:
            subprocess.check_call(
                ["npm", "init", "-y"], shell=True, cwd=_REPO_ROOT,
                stdout=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            _log.error("[preflight] npm init failed: %s", e)
            return False

    mcp_installed = os.path.isdir(
        os.path.join(node_modules, "@playwright", "mcp")
    )
    if not mcp_installed:
        _log.info("[preflight] Installing @playwright/mcp locally (one-time)...")
        try:
            subprocess.check_call(
                ["npm", "install", "@playwright/mcp"],
                shell=True, cwd=_REPO_ROOT,
            )
        except subprocess.CalledProcessError as e:
            _log.error("[preflight] npm install failed: %s", e)
            return False

    _log.info("[preflight] Ensuring Chromium matches @playwright/mcp's Playwright version...")
    # Use the Playwright CLI bundled WITH @playwright/mcp so the browser build matches
    # its pinned version exactly. A plain `npx playwright install` can resolve a
    # different (hoisted) Playwright and fetch the wrong Chromium build.
    mcp_cli = os.path.join(
        node_modules, "@playwright", "mcp", "node_modules", "playwright", "cli.js"
    )
    if not os.path.isfile(mcp_cli):
        mcp_cli = os.path.join(node_modules, "playwright", "cli.js")
    try:
        if os.path.isfile(mcp_cli):
            subprocess.check_call(["node", mcp_cli, "install", "chromium"], cwd=_REPO_ROOT)
        else:
            subprocess.check_call(
                ["npx", "playwright", "install", "chromium"], shell=True, cwd=_REPO_ROOT
            )
    except subprocess.CalledProcessError as e:
        _log.error("[preflight] Chromium install failed: %s", e)
        return False
    return True


def _slugify(text, fallback="app"):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or fallback


def _make_run_dir(base_url, persona_id="general"):
    """Create output/<app-slug>/<timestamp>/ (+ screenshots + video) and return paths."""
    host = urlparse(base_url).hostname or ""
    app_slug = _slugify(host.split(".")[0])
    run_id = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    if persona_id and persona_id != "general":
        run_id = f"{run_id}__{_slugify(persona_id)}"
    run_dir = os.path.join(_OUTPUT_DIR, app_slug, run_id)
    screenshots_dir = os.path.join(run_dir, "screenshots")
    video_dir = os.path.join(run_dir, "video")
    os.makedirs(screenshots_dir, exist_ok=True)
    os.makedirs(video_dir, exist_ok=True)
    return run_dir, screenshots_dir, video_dir, app_slug


def _write_mcp_config(run_dir, screenshots_dir, video_dir):
    """Write a per-run @playwright/mcp config that records the session to a webm.

    `contextOptions.recordVideo` makes Playwright capture the whole headed session;
    the file is finalized when the page/context closes (the agent is told to call
    `browser_close` as its final step).
    """
    config = {
        "browser": {
            "browserName": "chromium",
            "launchOptions": {"headless": False},
            "contextOptions": {
                "viewport": {"width": _RECORD_WIDTH, "height": _RECORD_HEIGHT},
                "recordVideo": {
                    "dir": video_dir,
                    "size": {"width": _RECORD_WIDTH, "height": _RECORD_HEIGHT},
                },
            },
        },
        "outputDir": screenshots_dir,
    }
    config_path = os.path.join(run_dir, "pw-mcp-config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config_path


def _relocate_stray_screenshots(run_dir, screenshots_dir, script_path):
    """Move screenshots the agent saved outside the run folder into screenshots/.

    Microsoft's @playwright/mcp resolves an explicit screenshot `filename` against its
    launch directory (the repo root), not our configured output dir. So a call like
    `browser_take_screenshot(filename="command-center.png")` lands in the repo root. We
    move every PNG the demo script references into the run's screenshots/ folder so the
    parser and the video slicer can find them. A same-drive move preserves mtime, which
    keeps the slicer's per-feature cut points valid.
    """
    if not os.path.isfile(script_path):
        return 0
    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read()
    referenced = {os.path.basename(m) for m in re.findall(r"[A-Za-z0-9][\w.-]*\.png", text)}
    if not referenced:
        return 0
    search_dirs = [_REPO_ROOT, run_dir]
    moved = 0
    for name in referenced:
        dest = os.path.join(screenshots_dir, name)
        if os.path.isfile(dest):
            continue
        for base in search_dirs:
            cand = os.path.join(base, name)
            if os.path.isfile(cand):
                try:
                    shutil.move(cand, dest)
                    moved += 1
                except OSError:
                    pass
                break
    if moved:
        _log.info("[screenshots] Relocated %d screenshot(s) into %s", moved, screenshots_dir)
    return moved


def _finalize_session_video(video_dir, timeout=20.0):
    """Wait for Playwright to flush the session webm, then normalize its name.

    Playwright writes the video asynchronously on context close, so we poll briefly.
    Returns the path to the recording (renamed to session.webm) or None.
    """
    deadline = time.time() + timeout
    webm = None
    while time.time() < deadline:
        candidates = glob.glob(os.path.join(video_dir, "*.webm"))
        if candidates:
            webm = max(candidates, key=os.path.getmtime)
            # Ensure the file has stopped growing before we treat it as complete.
            size1 = os.path.getsize(webm)
            time.sleep(0.75)
            if os.path.getsize(webm) == size1:
                break
        else:
            time.sleep(0.5)
    if not webm or not os.path.isfile(webm):
        _log.info("[video] No session recording was produced.")
        return None
    session_path = os.path.join(video_dir, "session.webm")
    if os.path.abspath(webm) != os.path.abspath(session_path):
        try:
            if os.path.isfile(session_path):
                os.remove(session_path)
            os.replace(webm, session_path)
        except OSError:
            session_path = webm
    _log.info("[video] Session recording: %s", session_path)
    return session_path


def _build_agent_input(base_url, spec_text, username, password, mfa_code, screenshots_dir, persona=None):
    lines = [
        "You are being invoked to generate a presenter demo script for a web app.\n",
        f"BASE URL: {base_url}",
    ]
    creds = []
    if username:
        creds.append(f"USERNAME / EMAIL: {username}")
    if password:
        creds.append(f"PASSWORD: {password}")
    if mfa_code:
        creds.append(f"MFA / OTP CODE: {mfa_code}")
    if creds:
        lines.append("SIGN-IN CREDENTIALS (use only if the app shows a login screen):")
        lines.extend("  " + c for c in creds)
    else:
        lines.append(
            "SIGN-IN CREDENTIALS: none provided — if the app has no login, just proceed; "
            "if it requires one, report that you cannot sign in."
        )
    lines.append(
        f"SCREENSHOTS DIR (the browser's output directory — screenshots you take are "
        f"saved here automatically; pass only a short filename): {screenshots_dir}\n"
    )
    lines.append(
        "Follow the phases in your instructions: get into the app (sign in only if "
        "needed), explore broadly (capturing one screenshot of each feature page), then "
        "write the narration script to demo-script.md via the filesystem MCP. When you "
        "are completely done, close the browser so the session recording is saved.\n"
    )
    persona_instructions = ((persona or {}).get("instructions") or "").strip()
    if persona_instructions:
        lines.append(
            f"----- TARGET AUDIENCE LENS: {persona.get('name', '')} -----"
        )
        lines.append(
            "Explore and prioritise the app through this lens so the resulting script "
            "has the depth this audience cares about:"
        )
        lines.append(persona_instructions)
        lines.append("----- END TARGET AUDIENCE LENS -----")
    spec = (spec_text or "").strip()
    if spec:
        lines.append("----- SPECIFICATION DOCUMENT (verbatim) -----")
        lines.append(spec)
        lines.append("----- END SPECIFICATION DOCUMENT -----")
    else:
        lines.append("No specification document was provided — infer intent from the UI.")
    return "\n".join(lines) + "\n"


async def _run_agent(config, file_server, automation_server, agent_input):
    with open(_INSTRUCTIONS_PATH, "r", encoding="utf-8") as f:
        instructions = f.read()

    client = AsyncAzureOpenAI(
        api_key=config.openai_api_key,
        azure_endpoint=config.openai_endpoint,
        api_version=config.openai_api_version,
    )
    set_default_openai_client(client)
    set_tracing_disabled(disabled=True)

    agent = Agent(
        name="Demo Narrator",
        instructions=instructions,
        mcp_servers=[file_server, automation_server],
        model=OpenAIChatCompletionsModel(
            model=config.openai_deployment,
            openai_client=client,
        ),
    )

    result = await Runner.run(
        starting_agent=agent,
        input=agent_input,
        max_turns=MAX_TURNS,
    )
    _log.info("Agent finished. Final output:\n%s", result.final_output)


async def explore(config, base_url, spec_text="", username="", password="", mfa_code="", persona=None):
    """Run the exploration agent; return (run_dir, app_slug, script_path).

    Credentials, spec, and persona are all optional — the agent signs in only if the
    app shows a login screen and infers intent from the UI when no spec is given. When
    a persona is provided its lens steers what the agent digs into. script_path points
    at demo-script.md and may not exist if the agent failed.
    """
    if not shutil.which("npm") or not shutil.which("npx"):
        raise RuntimeError("npm/npx not found on PATH. Install Node.js and retry.")

    if not _ensure_playwright_mcp():
        raise RuntimeError("Playwright preflight failed; see messages above.")

    persona_id = (persona or {}).get("id", "general")
    run_dir, screenshots_dir, video_dir, app_slug = _make_run_dir(base_url, persona_id)
    mcp_config_path = _write_mcp_config(run_dir, screenshots_dir, video_dir)
    agent_input = _build_agent_input(
        base_url, spec_text, username, password, mfa_code, screenshots_dir, persona
    )
    _log.info("This run's output folder: %s", run_dir)

    _log.info("Starting MCP servers (filesystem + Playwright)...")
    async with MCPServerStdio(
        name="Filesystem Server",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", run_dir],
        },
        cache_tools_list=True,
    ) as file_server, MCPServerStdio(
        name="Playwright Server",
        params={
            "command": "npx",
            "args": ["--no-install", "@playwright/mcp", "--config", mcp_config_path],
            "cwd": _REPO_ROOT,
        },
        cache_tools_list=True,
    ) as automation_server:
        fs_tools = await file_server.list_tools()
        _log.debug("Filesystem tools: %s", [t.name for t in fs_tools])
        pw_tools = await automation_server.list_tools()
        _log.debug("Playwright tools: %s", [t.name for t in pw_tools])

        await _run_agent(config, file_server, automation_server, agent_input)

    # @playwright/mcp writes explicit-filename screenshots to the repo root, not our
    # output dir; move them into screenshots/ so the parser and slicer can find them.
    _relocate_stray_screenshots(run_dir, screenshots_dir, os.path.join(run_dir, "demo-script.md"))

    # Playwright flushes the recording on context close; normalize it to session.webm.
    _finalize_session_video(video_dir)

    script_path = os.path.join(run_dir, "demo-script.md")
    return run_dir, app_slug, script_path
