const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "")

export type JobSnapshot = {
  job_id: string
  status: "queued" | "running" | "completed" | "failed"
  stage: "queued" | "exploring" | "narrating" | "rendering" | "completed" | "failed"
  make_video: boolean
  dry_run: boolean
  artifacts: Record<string, string>
  error: string | null
  screenshots?: string[]
  message?: string
  progress?: number
  heartbeat?: number
  started_at?: string
  run_timestamp?: string | null
}

export type CreateJobPayload = {
  base_url: string
  spec_text: string
  username: string
  password: string
  mfa_code: string
  make_video: boolean
  dry_run: boolean
  format: "md" | "html"
}

export type HistoryRun = {
  app_slug: string
  run_id: string
  run_timestamp: string
  artifacts: Record<string, string>
  screenshots: string[]
  status: "completed" | "in_progress"
  stage?: JobSnapshot["stage"]
  progress?: number
  message?: string
  job_id?: string
  duration_seconds?: number
  duration_label?: string
  screenshot_count?: number
}

export async function createJob(payload: CreateJobPayload): Promise<{ job_id: string }> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new Error(`Cannot reach the API at ${API_BASE}. Start uvicorn on port 8000 and reload this page.`)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || "Could not start the run")
  }
  return response.json()
}

export async function getJob(id: string): Promise<JobSnapshot> {
  const response = await fetch(`${API_BASE}/api/jobs/${id}`)
  if (!response.ok) {
    if (response.status === 404) throw new Error("This run is no longer available. The API was restarted; start a new run.")
    throw new Error("Could not load this run")
  }
  return response.json()
}

export async function getScriptText(id: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/jobs/${id}/script`)
  if (!response.ok) throw new Error("Transcript is not ready yet")
  return response.text()
}

export async function getHistory(): Promise<HistoryRun[]> {
  const response = await fetch(`${API_BASE}/api/history`)
  if (!response.ok) throw new Error("Could not load run history")
  return response.json()
}

export async function getHistoryScript(run: HistoryRun): Promise<string> {
  const response = await fetch(historyArtifactUrl(run, "talking-script"))
  if (!response.ok) throw new Error("Could not load the historical transcript")
  return response.text()
}

export function videoUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/video`
}

export function artifactUrl(id: string, name: string): string {
  return `${API_BASE}/api/jobs/${id}/artifacts/${encodeURIComponent(name)}`
}

export function jobScreenshotUrl(id: string, name: string): string {
  return `${API_BASE}/api/jobs/${encodeURIComponent(id)}/screenshots/${encodeURIComponent(name)}`
}

export function historyArtifactUrl(run: HistoryRun, name: string): string {
  return `${API_BASE}/api/history/${encodeURIComponent(run.app_slug)}/${encodeURIComponent(run.run_id)}/artifacts/${encodeURIComponent(name)}`
}

export function historyScreenshotUrl(run: HistoryRun, name: string): string {
  return `${API_BASE}/api/history/${encodeURIComponent(run.app_slug)}/${encodeURIComponent(run.run_id)}/artifacts/screenshots/${encodeURIComponent(name)}`
}

export function subscribeToJob(id: string, onEvent: (event: string, snapshot: JobSnapshot) => void): () => void {
  const source = new EventSource(`${API_BASE}/api/jobs/${id}/events`)
  let finished = false
  const pollTimer = window.setInterval(async () => {
    try {
      const snapshot = await getJob(id)
      onEvent("poll", snapshot)
      if (snapshot.status === "completed" || snapshot.status === "failed") {
        finished = true
        window.clearInterval(pollTimer)
        source.close()
        onEvent(snapshot.status === "completed" ? "done" : "error", snapshot)
      }
    } catch (error) {
      if (error instanceof Error && error.message.startsWith("This run is no longer available")) {
        finished = true
        window.clearInterval(pollTimer)
        source.close()
        onEvent("error", { error: error.message, stage: "failed", status: "failed" } as JobSnapshot)
      }
    }
  }, 3000)
  const handle = (event: MessageEvent) => onEvent(event.type, JSON.parse(event.data) as JobSnapshot)
  ;["snapshot", "stage", "heartbeat", "done", "error"].forEach((name) => source.addEventListener(name, handle))
  source.addEventListener("done", () => { finished = true; window.clearInterval(pollTimer) })
  source.addEventListener("error", () => { if (finished) window.clearInterval(pollTimer) })
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED && !finished) onEvent("heartbeat", { error: null, stage: "queued", status: "running", message: "Reconnecting to the run..." } as JobSnapshot)
  }
  return () => { finished = true; window.clearInterval(pollTimer); source.close() }
}
