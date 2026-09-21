# PitchPilot

> **Autopilot for product demos — point it at any app, get a narrated walkthrough.**

**PitchPilot turns any web application into a polished, narrated demo video.** It
autonomously explores the live app, understands its functional flow, writes a
presenter-quality script in the product's own language, and narrates it with Azure
AI Speech over the captured screens — collapsing hours of demo prep into minutes.

## Why it matters

**The problem:** Great software often demos poorly. Whoever has to present an app —
an account manager, a founder, a support lead — frequently lacks the domain
knowledge to walk through it convincingly, so the demo undersells the build.

**PitchPilot is autopilot for product demos.** Point it at any web app (URL +
optional spec) and it:

1. **Explores** the live interface autonomously via an agent (Playwright + MCP),
   capturing every key screen.
2. **Understands** the functional flow, internalising any specification so it
   speaks in the customer's terminology — not generic filler.
3. **Scripts** a presenter-grade walkthrough that any non-expert can confidently
   deliver.
4. **Produces** a narrated video with Azure AI Text-to-Speech, motion, transitions,
   and music.

The result is a ready-to-share artifact that makes demo quality **consistent
regardless of who's in the room** — and it scales to any app, any domain, any
language.

## What makes it stand out

- **Impact** — Removes a universal bottleneck: *"can you walk us through the app?"*
  Every team that ships software needs this, and consistent demos protect the value
  of what was built.
- **Innovation** — Not another screen recorder. PitchPilot is an **agent that
  comprehends an unfamiliar app** and generates domain-accurate narration —
  understanding, not just capture.
- **Technical depth** — A multi-stage agentic pipeline: autonomous exploration
  (MCP + Playwright) → functional-flow reasoning (LLM) → script generation → speech
  synthesis → automated video composition. A real, working end-to-end system.
- **Scalability** — App- and domain-agnostic by design. One pipeline serves sales
  enablement, onboarding, release notes, support, accessibility, and localisation
  (multilingual voices built in).
- **Azure-native** — Built on Azure OpenAI + Azure AI Speech, with a clean
  enterprise-adoption and cost-control story.

> *"Every company can build impressive software. Almost none can demo it
> consistently. PitchPilot puts every product demo on autopilot — any app, any
> language, in minutes."*
>
> - *"Screen recorders capture what you do. PitchPilot understands what the app is."*
> - *"Hours of a domain expert's time → a 2-minute video, automatically."*
> - *"One pipeline, any web app, any domain, any language."*

## How it works

```mermaid
flowchart TD
    USER(["URL + optional spec"]) --> ENTRY["pitchpilot.py<br/>single entry point"]

    subgraph CORE["core engine"]
        direction LR
        S1["1 · Explore<br/>Playwright + MCP agent"] --> S2["2 · Narrate<br/>talking script"] --> S3["3 · Render<br/>TTS + video compose"]
    end

    ENTRY --> S1
    S1 & S2 --> AOAI["Azure OpenAI"]
    S3 --> SPEECH["Azure AI Speech"]

    S2 --> TRANSCRIPT[/"talking-script.json + .md"/]
    S3 --> VIDEO[/"demo-video.mp4"/]
    TRANSCRIPT -. "--from-script (resume, no re-scrape)" .-> S3

    subgraph EXPERIENCE["Local browser experience"]
        direction LR
      WEB["Web UI<br/>React + Vite"] --> API["API<br/>FastAPI + background jobs + SSE"]
    end
    API -->|"calls the same engine"| S1

    classDef entry fill:#4f46e5,stroke:#3730a3,color:#ffffff;
    classDef stage fill:#2563eb,stroke:#1e40af,color:#ffffff;
    classDef azure fill:#0e7490,stroke:#155e75,color:#ffffff;
    classDef output fill:#059669,stroke:#047857,color:#ffffff;
    classDef experience fill:#cbd5e1,stroke:#64748b,color:#0f172a;

    class ENTRY entry;
    class S1,S2,S3 stage;
    class AOAI,SPEECH azure;
    class TRANSCRIPT,VIDEO output;
    class WEB,API experience;
```

## Browser UI and API

PitchPilot also includes a local browser experience over the same core engine:

- **New run form** accepts an app URL, optional sign-in details, an MFA code, and
  a `.md` or `.txt` product spec.
- **Output choices** let you create a transcript only, or a transcript plus video.
  Video runs can use **Dry run** to skip paid Azure Speech synthesis.
- **Live progress** updates Explore, Narrate, and Render stages through Server-Sent
  Events (SSE), with a polling fallback.
- **Results** provide a full-width HTML presenter-script view, Markdown transcript,
  generated artifacts, screenshot count, and video preview/download when requested.
- **Run history** reads prior local output folders so completed demos remain easy to
  inspect after a browser refresh. Each completed run opens in the same tabbed detail
  view as a fresh result.
- **Download all** packages the full run folder into one ZIP, including scripts,
  screenshots, narration clips, and the video when present. Active jobs themselves
  are in-memory and are lost when the API restarts.

The API is a local FastAPI service. It starts one background pipeline task per
browser run and serves the generated transcript, video, HTML script, and screenshots.
The React/Vite frontend defaults to `http://127.0.0.1:8000`; override that with
`VITE_API_BASE` when needed.

### Browser UI

The UI keeps the primary demo workflow in one place: configure a target, monitor
the run, then review or download its output.

![PitchPilot new-run browser UI](assets/readme/browser-ui-new-run.png)

Past output stays useful after the original job has finished. History lists the
saved artifacts and provides a detail view for each completed run.

![PitchPilot run-history browser UI](assets/readme/browser-ui-history.png)

The detail view provides the generated HTML script, transcript, artifacts, optional
video, and a single **Download all** ZIP for the full run.

![PitchPilot saved-run detail browser UI](assets/readme/browser-ui-run-detail.png)

### Captured-screen example

PitchPilot captures the screens it visits and uses them in the generated demo
artifacts. This example came from a completed CarePath Storage run:

![Captured Command Center screen](output/carepathstorage/2026-09-20_185428/screenshots/command-center-2026-09-20T13-25-34-140Z.png)

## One entry point, flag-driven

Everything runs through `pitchpilot.py`:

```powershell
# Stages 1 + 2: explore the app and write the talking transcript
python pitchpilot.py

# Stages 1 + 2 + 3: also render the narrated MP4
python pitchpilot.py --video

# Stage 3 only: render the video from an existing transcript (no re-scrape, no LLM)
python pitchpilot.py --from-script "output\<app-slug>\<timestamp>\talking-script.json" --video

# Silent preview (skips billable Text-to-Speech)
python pitchpilot.py --video --dry-run
```

| Flag | Effect |
| --- | --- |
| _(none)_ | Explore the app, then write `talking-script.json` / `.md`. Stops there. |
| `--video` | Also synthesize narration and compose `demo-video.mp4`. |
| `--from-script PATH` | Skip scraping + narration; render the video straight from an existing `talking-script.json`. |
| `--dry-run` | Compose a silent preview without calling Azure Text-to-Speech. |
| `--format md\|html` | Output format for the presenter demo script (default `md`). |

The transcript-only run prints the exact `--from-script` command to make the
video later, so you never re-run the whole pipeline just to render.

## Pipeline

1. **Explore** — Playwright MCP + an Azure OpenAI agent log in, walk the app, and
   write `demo-script.md` + one screenshot per feature.
2. **Narrate** — Azure OpenAI rewrites the presenter notes into an organic spoken
   script (`talking-script.json` + a readable `talking-script.md`).
3. **Render** — Azure Text-to-Speech voices each segment; MoviePy composites the
   narration over the screenshots (Ken Burns, crossfades, optional music) into
   `demo-video.mp4`.

Every artifact for a run lands in one folder:

```
output/<app-slug>/<timestamp>/
    demo-script.md          # presenter script
    demo-script.html        # polished HTML (when --format html)
    screenshots/            # one image per feature page
    talking-script.json     # machine-readable narration (drives synthesis)
    talking-script.md       # human-readable review copy
    clips/segment_XXX.mp3    # per-segment narration audio (skipped on --dry-run)
    demo-video.mp4          # final video (with --video)
output/<app-slug>/latest.html   # standalone shareable script (screenshots embedded)
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.template .env    # then fill in Azure OpenAI + Speech values
```

Requires **Node.js** on `PATH` (`npx` launches the Playwright + filesystem MCP
servers) and **Python 3.11–3.13**. ffmpeg is provided by the bundled
`imageio-ffmpeg`, so no separate install is needed.

## Run locally

The browser UI and API are separate local processes. Open two PowerShell terminals
from the repository root.

```powershell
# Terminal 1: install API dependencies once, then start the API
pip install -r requirements.txt -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

```powershell
# Terminal 2: install UI dependencies once, then start Vite
cd web
npm install
npm run dev
```

Open `http://localhost:5173` in a browser. Enter a reachable app URL, add a spec
or credentials only when the target needs them, choose the output, and select
**Generate demo**. PitchPilot opens Chromium to explore the target application;
run the API in an interactive desktop session with Node.js available on `PATH`.

Generated files are written to `output/<app-slug>/<timestamp>/`. The UI's History
view lists those local runs and their available artifacts.

### Example scenario: CarePath Storage

Use this example to demonstrate the complete PitchPilot workflow for a healthcare
operations product:

1. Enter the CarePath Storage URL in the browser UI.
2. Paste the following into **Spec document**:

```text
Create a 60-second walkthrough for a healthcare operations director.

Start at Command Center to establish visibility into operational priorities.
Then show Cohort Explorer and Exception Cohorts to explain how teams identify
patient groups and cases requiring intervention. Include Denial Prevention to
connect proactive workflows with reimbursement protection. Finish with
Configuration to show that each organisation can adapt the workflow.

Use short, natural voice-over sentences and focus on business outcomes.
End with: "CarePath Storage turns operational signals into focused action."
```

3. Select **Transcript only** for a fast script review, or select **Transcript +
  video** with **Dry run** enabled to validate rendering without Azure Speech cost.
4. When the run completes, read the HTML script or transcript, preview the video if
  generated, and use **Download all** to save the complete set of deliverables.
5. Open **History** later and choose **View details** on the saved run to revisit the
  same tabs and downloads.

### Test locally

1. Start the API and UI using the commands above, then open the browser UI.
2. Submit a known reachable URL with **Transcript only**. Confirm the progress view
  reaches Explore and Narrate, then confirm the Result page shows the HTML view,
  transcript, individual artifacts, and the **Download all** ZIP.
3. Submit another run with **Transcript + video** and **Dry run** enabled. Confirm
  the Render stage completes and the Result page has a playable/downloadable MP4.
  Dry runs avoid Azure Speech charges.
4. Use **History** to verify the completed run, screenshots, and artifacts remain
  available after refreshing the browser. Open **View details** and confirm the
  historical **Download all** ZIP works too.
5. Confirm the frontend compiles without type errors:

```powershell
cd web
npm run build
```

For an API-only check during development, open `http://127.0.0.1:8000/docs` after
starting Uvicorn. FastAPI exposes the interactive endpoint documentation there.

## Layout

```
pitchpilot.py     # single entry point (flags above)
core/             # the engine — explorer, narration, TTS, compositor
assets/music/     # optional royalty-free background music
api/              # FastAPI service, in-memory jobs, SSE progress, artifact routes
web/              # React + Vite browser UI for creating and reviewing runs
```

The API and web layers call the existing `core/` engine; the command-line workflow
remains available when you prefer to run the pipeline directly.
