# Web UI (reserved)

This folder is scaffolding for the **PitchPilot web UI** — not yet implemented.

**Planned:** a **React + Tailwind** (professional theme) single-page app that talks
to the `api/` service to submit runs and watch progress.

Suggested first screens (starting point, adjust as needed):

- **New run** — enter app URL + optional spec, choose "transcript only" or "+ video".
- **Job status** — live progress through explore → narrate → render.
- **Result** — preview the talking script and play / download `demo-video.mp4`.

The UI should never call the engine directly — it goes through the `api/` layer,
which owns job orchestration and background processing.

> Delete this file once real code lands here.
