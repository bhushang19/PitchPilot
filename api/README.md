# API layer (reserved)

> **Build guide:** see [`docs/BUILD-API-AND-WEB.md`](../docs/BUILD-API-AND-WEB.md) —
> hand it to GitHub Copilot to build this layer.

This folder is scaffolding for the **PitchPilot API** — not yet implemented.

**Planned:** a **FastAPI** service that wraps the `core/` engine and runs the
pipeline as **background jobs** (job submission + status polling), so the web UI
can kick off runs without blocking.

Suggested endpoints (starting point, adjust as needed):

- `POST /jobs` — submit a run (`base_url`, spec, `--video` flag) → returns a job id.
- `GET /jobs/{id}` — job status + progress (exploring / narrating / rendering).
- `GET /jobs/{id}/artifacts` — links to `talking-script.*`, `demo-video.mp4`.

Call the engine directly — reuse, don't reimplement:

- `core.explorer.explore(...)` — stage 1 (explore → demo-script.md)
- `core.script_generator.generate_talking_script(...)` — stage 2 (talking script)
- `core.video.render_video(...)` / `core.video.render_from_script(...)` — stage 3

> Delete this file once real code lands here.
