"""Stage 1 — explore a web app and write a presenter demo script.

Drives Playwright MCP + a filesystem MCP through an Azure OpenAI agent to log in,
explore the app, and produce `demo-script.md` (+ one screenshot per feature) in a
timestamped run folder. Ported from the reference narrator so behaviour matches.
"""

import asyncio
import datetime
import os
import re
import shutil
import subprocess
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

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_OUTPUT_DIR = os.path.join(_REPO_ROOT, "output")
_INSTRUCTIONS_PATH = os.path.join(_HERE, "agent_instructions.txt")

MAX_TURNS = 100


def _ensure_playwright_chromium():
    """Install the MCP server + its exact Chromium locally to avoid version mismatch.

    A global `npx playwright install chromium` pulls the latest Playwright's browser,
    which won't match the MCP server's pinned Playwright. We install the MCP server
    into a local node_modules and run `playwright install chromium` from there so the
    versions align by construction. Both steps are idempotent.
    """
    node_modules = os.path.join(_REPO_ROOT, "node_modules")
    pkg_json = os.path.join(_REPO_ROOT, "package.json")

    if not os.path.isfile(pkg_json):
        print("[preflight] Creating local package.json...")
        try:
            subprocess.check_call(
                ["npm", "init", "-y"], shell=True, cwd=_REPO_ROOT,
                stdout=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            print(f"[preflight] npm init failed: {e}")
            return False

    mcp_installed = os.path.isdir(
        os.path.join(node_modules, "@executeautomation", "playwright-mcp-server")
    )
    if not mcp_installed:
        print("[preflight] Installing @executeautomation/playwright-mcp-server locally (one-time)...")
        try:
            subprocess.check_call(
                ["npm", "install", "@executeautomation/playwright-mcp-server"],
                shell=True, cwd=_REPO_ROOT,
            )
        except subprocess.CalledProcessError as e:
            print(f"[preflight] npm install failed: {e}")
            return False

    print("[preflight] Ensuring Chromium matches the local Playwright version...")
    try:
        subprocess.check_call(
            ["npx", "playwright", "install", "chromium"],
            shell=True, cwd=_REPO_ROOT,
        )
    except subprocess.CalledProcessError as e:
        print(f"[preflight] Chromium install failed: {e}")
        return False
    return True


def _slugify(text, fallback="app"):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or fallback


def _make_run_dir(base_url):
    """Create output/<app-slug>/<timestamp>/ (+ screenshots) and return the paths."""
    host = urlparse(base_url).hostname or ""
    app_slug = _slugify(host.split(".")[0])
    run_id = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = os.path.join(_OUTPUT_DIR, app_slug, run_id)
    screenshots_dir = os.path.join(run_dir, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    return run_dir, screenshots_dir, app_slug


def _build_agent_input(base_url, password, spec_text, screenshots_dir):
    return (
        "You are being invoked to generate a presenter demo script for a web app.\n\n"
        f"BASE URL: {base_url}\n"
        f"ADMIN PASSWORD: {password}\n"
        "MFA CODE (mock): 123456\n"
        f"SCREENSHOTS DIR (absolute path — save every page screenshot here): {screenshots_dir}\n\n"
        "Follow the phases in your instructions: log in, explore broadly (capturing a "
        "screenshot of each feature page), then write the narration script to "
        "demo-script.md via the filesystem MCP.\n\n"
        "----- SPECIFICATION DOCUMENT (verbatim) -----\n"
        f"{spec_text}\n"
        "----- END SPECIFICATION DOCUMENT -----\n"
    )


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
    print(f"\nAgent finished. Final output:\n{result.final_output}")


async def explore(config, base_url, password, spec_text):
    """Run the exploration agent; return (run_dir, app_slug, script_path).

    script_path points at demo-script.md and may not exist if the agent failed.
    """
    if not shutil.which("npm") or not shutil.which("npx"):
        raise RuntimeError("npm/npx not found on PATH. Install Node.js and retry.")

    if not _ensure_playwright_chromium():
        raise RuntimeError("Playwright preflight failed; see messages above.")

    run_dir, screenshots_dir, app_slug = _make_run_dir(base_url)
    agent_input = _build_agent_input(base_url, password, spec_text, screenshots_dir)
    print(f"\nThis run's output folder: {run_dir}")

    print("\nStarting MCP servers (filesystem + Playwright)...\n")
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
            "args": ["--no-install", "@executeautomation/playwright-mcp-server"],
            "cwd": _REPO_ROOT,
        },
        cache_tools_list=True,
    ) as automation_server:
        fs_tools = await file_server.list_tools()
        print(f"Filesystem tools: {[t.name for t in fs_tools]}")
        pw_tools = await automation_server.list_tools()
        print(f"Playwright tools: {[t.name for t in pw_tools]}\n")

        await _run_agent(config, file_server, automation_server, agent_input)

    script_path = os.path.join(run_dir, "demo-script.md")
    return run_dir, app_slug, script_path
