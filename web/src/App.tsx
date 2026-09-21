import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ArrowRight,
  Check,
  CircleDot,
  Download,
  FileCheck,
  FileText,
  LoaderCircle,
  Moon,
  Play,
  ShieldCheck,
  Sparkles,
  Sun,
  Upload,
  Video,
  WandSparkles,
} from "lucide-react";
import { toast } from "sonner";
import {
  artifactUrl,
  createJob,
  getHistory,
  getHistoryScript,
  getJob,
  getScriptText,
  historyArtifactUrl,
  historyDownloadUrl,
  historyScreenshotUrl,
  jobDownloadUrl,
  jobScreenshotUrl,
  subscribeToJob,
  videoUrl,
  type CreateJobPayload,
  type HistoryRun,
  type JobSnapshot,
} from "./lib/api";

type View = "new" | "progress" | "result" | "history" | "history-detail";
const steps = ["exploring", "narrating", "rendering"] as const;

const initialForm: CreateJobPayload = {
  base_url: "",
  spec_text: "",
  username: "",
  password: "",
  mfa_code: "",
  make_video: true,
  dry_run: false,
  format: "md",
};

export default function App() {
  const [view, setView] = useState<View>("new");
  const [form, setForm] = useState(initialForm);
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [script, setScript] = useState("");
  const [history, setHistory] = useState<HistoryRun[]>([]);
  const [selectedHistoryRun, setSelectedHistoryRun] =
    useState<HistoryRun | null>(null);
  const [historyScript, setHistoryScript] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [dark, setDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const unsubscribe = useRef<(() => void) | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => () => unsubscribe.current?.(), []);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const jobId = job.job_id;

    async function refreshActiveJob() {
      if (document.visibilityState !== "visible") return;
      try {
        const snapshot = await getJob(jobId);
        setJob(snapshot);
        if (snapshot.status === "completed") {
          toast.success("Your demo is ready");
          setView("result");
          void loadScript(jobId);
        }
        if (snapshot.status === "failed") {
          toast.error(snapshot.error || "The run failed");
        }
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : "Could not refresh this run",
        );
      }
    }

    document.addEventListener("visibilitychange", refreshActiveJob);
    return () =>
      document.removeEventListener("visibilitychange", refreshActiveJob);
  }, [job?.job_id, job?.status]);

  function update<K extends keyof CreateJobPayload>(
    key: K,
    value: CreateJobPayload[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function startRun(event: React.FormEvent) {
    event.preventDefault();
    if (!form.base_url) return toast.error("Enter an app URL to explore.");
    setSubmitting(true);
    try {
      new URL(form.base_url);
    } catch {
      return toast.error("Use a complete URL, such as https://app.example.com");
    }
    try {
      const created = await createJob(form);
      setJob({
        job_id: created.job_id,
        status: "queued",
        stage: "queued",
        make_video: form.make_video,
        dry_run: form.dry_run,
        artifacts: {},
        error: null,
      });
      setView("progress");
      unsubscribe.current = subscribeToJob(
        created.job_id,
        (eventName, snapshot) => {
          setJob(snapshot);
          if (eventName === "error") {
            toast.error(snapshot.error || "The run failed");
          }
          if (eventName === "done") {
            toast.success("Your demo is ready");
            setView("result");
            loadScript(created.job_id);
          }
        },
      );
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not start the run",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function loadScript(id: string) {
    try {
      setScript(await getScriptText(id));
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not load the transcript",
      );
    }
  }

  function startAnother() {
    unsubscribe.current?.();
    unsubscribe.current = null;
    setForm({ ...initialForm });
    setJob(null);
    setScript("");
    setHistory([]);
    setHistoryLoading(false);
    setSubmitting(false);
    setView("new");
  }

  async function showHistory() {
    setView("history");
    setHistoryLoading(true);
    try {
      setHistory(await getHistory());
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not load run history",
      );
    } finally {
      setHistoryLoading(false);
    }
  }

  async function openHistoryRun(run: HistoryRun) {
    setSelectedHistoryRun(run);
    setHistoryScript("");
    setView("history-detail");
    try {
      setHistoryScript(await getHistoryScript(run));
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not load the historical transcript",
      );
    }
  }

  const settled = job?.status === "completed" || job?.status === "failed";

  return (
    <div className="min-h-screen overflow-hidden bg-slate-50 text-slate-950 transition-colors dark:bg-[#0b1120] dark:text-slate-100">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-5 py-6 sm:px-8">
        <button
          className="brand"
          onClick={startAnother}
          aria-label="Start a new run"
        >
          <span className="brand-mark">
            <Sparkles size={17} />
          </span>
          <span>PitchPilot</span>
          <span className="hidden border-l border-slate-300 pl-3 text-xs font-normal text-slate-500 dark:border-slate-700 dark:text-slate-400 sm:inline">
            Autopilot for product demos.
          </span>
        </button>
        <div className="header-actions">
          <button className="history-button" onClick={showHistory}>
            <CircleDot size={15} /> History
          </button>
          <button
            className="icon-button"
            onClick={() => setDark((current) => !current)}
            aria-label={dark ? "Use light theme" : "Use dark theme"}
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-7xl px-5 pb-20 sm:px-8">
        <div className="mb-10 flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          <span
            className={
              view === "new" ? "text-indigo-600 dark:text-indigo-400" : ""
            }
          >
            01 Configure
          </span>
          <span className="h-px w-8 bg-slate-200 dark:bg-slate-800" />
          <span
            className={
              view === "progress" ? "text-indigo-600 dark:text-indigo-400" : ""
            }
          >
            02 Generate
          </span>
          <span className="h-px w-8 bg-slate-200 dark:bg-slate-800" />
          <span
            className={
              view === "result" ? "text-indigo-600 dark:text-indigo-400" : ""
            }
          >
            03 Review
          </span>
        </div>
        {view === "new" && (
          <NewRun
            form={form}
            update={update}
            onSubmit={startRun}
            submitting={submitting}
          />
        )}
        {view === "progress" && job && (
          <Progress job={job} onBack={startAnother} />
        )}
        {view === "result" && job && (
          <Result job={job} script={script} onNew={startAnother} />
        )}
        {view === "history" && (
          <HistoryView
            runs={history}
            loading={historyLoading}
            onNew={startAnother}
            onOpen={openHistoryRun}
          />
        )}
        {view === "history-detail" && selectedHistoryRun && (
          <HistoryDetail
            run={selectedHistoryRun}
            script={historyScript}
            onBack={showHistory}
            onNew={startAnother}
          />
        )}
        {view === "progress" && settled && job?.status === "failed" && (
          <button
            className="mt-6 text-sm font-semibold text-indigo-600"
            onClick={startAnother}
          >
            Start another run <ArrowRight className="inline" size={15} />
          </button>
        )}
      </main>
    </div>
  );
}

function NewRun({
  form,
  update,
  onSubmit,
  submitting,
}: {
  form: CreateJobPayload;
  update: <K extends keyof CreateJobPayload>(
    key: K,
    value: CreateJobPayload[K],
  ) => void;
  onSubmit: (event: React.FormEvent) => void;
  submitting: boolean;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  function readSpec(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".md") && !file.name.endsWith(".txt"))
      return toast.error("Choose a .md or .txt file");
    const reader = new FileReader();
    reader.onload = () => update("spec_text", String(reader.result));
    reader.readAsText(file);
  }
  return (
    <section className="grid items-start gap-12 lg:grid-cols-[0.75fr_1.25fr] lg:gap-24">
      <div className="pt-4 lg:pt-16">
        <div className="eyebrow">
          <WandSparkles size={14} /> DEMO STUDIO
        </div>
        <h1 className="hero-title">
          Turn a product tour into a story worth sharing.
        </h1>
        <p className="hero-copy">
          Give PitchPilot an app and a little context. It explores the
          experience, writes a polished presenter script, and can render the
          finished video.
        </p>
        <div className="mt-10 flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
          <ShieldCheck size={18} className="text-teal-600" /> Single-run, local
          workspace. Your credentials stay with this session.
        </div>
      </div>
      <form className="surface p-6 sm:p-8" onSubmit={onSubmit}>
        <div className="mb-8 flex items-start justify-between">
          <div>
            <h2 className="section-title">Start a new run</h2>
            <p className="muted mt-1">
              Set the destination and let the pilot take it from there.
            </p>
          </div>
          <div className="rounded-full bg-indigo-50 p-3 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-300">
            <Play size={18} fill="currentColor" />
          </div>
        </div>
        <label className="field-label">
          App URL <span className="required">Required</span>
          <input
            className="field"
            required
            type="url"
            placeholder="https://your-product.com"
            value={form.base_url}
            onChange={(event) => update("base_url", event.target.value)}
          />
        </label>
        <div className="my-7 border-t border-slate-200 dark:border-slate-800" />
        <p className="field-label mb-3">
          Sign-in details <span className="optional">Optional</span>
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field-label">
            Username / email
            <input
              className="field"
              value={form.username}
              onChange={(event) => update("username", event.target.value)}
            />
          </label>
          <label className="field-label">
            Password
            <input
              className="field"
              type="password"
              value={form.password}
              onChange={(event) => update("password", event.target.value)}
            />
          </label>
        </div>
        <label className="field-label mt-4">
          MFA / OTP code
          <input
            className="field"
            inputMode="numeric"
            value={form.mfa_code}
            onChange={(event) => update("mfa_code", event.target.value)}
          />
        </label>
        <label className="field-label mt-7">
          Spec document <span className="optional">Optional</span>
          <textarea
            className="field min-h-32 resize-y"
            placeholder="What should the demo emphasize?"
            value={form.spec_text}
            onChange={(event) => update("spec_text", event.target.value)}
          />
          <button
            type="button"
            className="upload-button"
            onClick={() => fileInput.current?.click()}
          >
            <Upload size={14} /> Load .md or .txt
          </button>
          <input
            ref={fileInput}
            hidden
            type="file"
            accept=".md,.txt,text/plain,text/markdown"
            onChange={readSpec}
          />
        </label>
        <div className="my-7 border-t border-slate-200 dark:border-slate-800" />
        <div className="choice-row">
          <div>
            <p className="field-label">Output</p>
            <p className="muted">Choose what the pilot produces.</p>
          </div>
          <div className="segmented">
            <button
              type="button"
              className={!form.make_video ? "selected" : ""}
              onClick={() => update("make_video", false)}
            >
              <FileText size={15} />
              Transcript only
            </button>
            <button
              type="button"
              className={form.make_video ? "selected" : ""}
              onClick={() => update("make_video", true)}
            >
              <Video size={15} />
              Transcript + video
            </button>
          </div>
        </div>
        {form.make_video && (
          <div className="choice-row mt-4 rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-900">
            <div>
              <p className="field-label">Dry run</p>
              <p className="muted">Skip paid speech synthesis.</p>
            </div>
            <button
              type="button"
              className={`toggle ${form.dry_run ? "on" : ""}`}
              role="switch"
              aria-checked={form.dry_run}
              onClick={() => update("dry_run", !form.dry_run)}
            >
              <span />
            </button>
          </div>
        )}
        <button
          className="primary-button mt-8 w-full"
          type="submit"
          disabled={submitting}
        >
          {submitting ? (
            <>
              <LoaderCircle className="spin" size={17} /> Starting run...
            </>
          ) : (
            <>
              Generate demo <ArrowRight size={17} />
            </>
          )}
        </button>
      </form>
    </section>
  );
}

function HistoryView({
  runs,
  loading,
  onNew,
  onOpen,
}: {
  runs: HistoryRun[];
  loading: boolean;
  onNew: () => void;
  onOpen: (run: HistoryRun) => void;
}) {
  const labels: Record<string, string> = {
    "demo-script": "Demo script",
    "demo-script-html": "Demo script HTML",
    "talking-script-json": "Talking script JSON",
    "talking-script": "Talking script",
    video: "Demo video",
  };
  const formatDuration = (run: HistoryRun) =>
    run.duration_label ||
    (run.duration_seconds
      ? `${Math.floor(run.duration_seconds / 60)}m ${run.duration_seconds % 60}s`
      : "Not available");
  return (
    <section className="mx-auto max-w-5xl pt-8">
      <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <div className="eyebrow">
            <CircleDot size={14} /> RUN HISTORY
          </div>
          <h1 className="hero-title">Your generated demos.</h1>
          <p className="hero-copy">
            Past runs and active runs are read from the local workspace.
          </p>
        </div>
        <button className="primary-button" onClick={onNew}>
          Configure new run <Sparkles size={16} />
        </button>
      </div>
      {loading ? (
        <div className="surface p-8">
          <p className="muted">Loading past runs...</p>
        </div>
      ) : runs.length === 0 ? (
        <div className="surface p-8">
          <p className="section-title">No runs yet</p>
          <p className="muted mt-2">Generated runs will appear here.</p>
        </div>
      ) : (
        <div className="history-grid">
          {runs.map((run) => {
            const active = run.status === "in_progress";
            const artifactHref = (name: string) =>
              active && run.job_id
                ? artifactUrl(run.job_id, name)
                : historyArtifactUrl(run, name);
            const screenshotHref = (name: string) =>
              active && run.job_id
                ? jobScreenshotUrl(run.job_id, name)
                : historyScreenshotUrl(run, name);
            const screenshotCount =
              run.screenshot_count ?? run.screenshots.length;
            return (
              <article
                className="history-card"
                key={`${run.app_slug}-${run.run_id}`}
              >
                <div className="history-card-top">
                  <div>
                    <p className="history-app">{run.app_slug}</p>
                    <p className="history-date">{run.run_timestamp}</p>
                  </div>
                  <span
                    className={`status ${active ? "status-active" : "status-success"}`}
                  >
                    {active ? "In progress" : "Complete"}
                  </span>
                </div>
                <p className="history-id">Run {run.run_id}</p>
                <p className="history-duration">
                  Total time <strong>{formatDuration(run)}</strong>
                </p>
                {!active && (
                  <button
                    className="secondary-button mt-4"
                    onClick={() => onOpen(run)}
                  >
                    View details <ArrowRight size={15} />
                  </button>
                )}
                {active && (
                  <div className="history-live">
                    <LoaderCircle className="spin" size={14} />{" "}
                    {run.message || "Working..."}
                    <strong>{run.progress ?? 0}%</strong>
                  </div>
                )}
                <div className="history-artifacts">
                  {Object.entries(run.artifacts).map(([name, path]) => (
                    <a
                      className="artifact-download"
                      href={artifactHref(name)}
                      target="_blank"
                      rel="noreferrer"
                      key={name}
                    >
                      <FileText size={14} />
                      <span>{labels[name] || name}</span>
                      <ArrowRight size={13} />
                      <span className="artifact-path">
                        {path.split(/[\\/]/).pop()}
                      </span>
                    </a>
                  ))}
                </div>
                <div className="history-screenshots">
                  <p className="screenshot-summary">
                    <FileCheck size={14} /> {screenshotCount} screenshot
                    {screenshotCount === 1 ? "" : "s"} captured
                  </p>
                  <div className="screenshot-links">
                    {run.screenshots.slice(0, 6).map((name) => (
                      <a
                        href={screenshotHref(name)}
                        target="_blank"
                        rel="noreferrer"
                        title={name}
                        key={name}
                      >
                        <img src={screenshotHref(name)} alt={name} />
                      </a>
                    ))}
                    {screenshotCount > run.screenshots.length && (
                      <span className="screenshot-more">
                        +{screenshotCount - run.screenshots.length} more
                      </span>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function HistoryDetail({
  run,
  script,
  onBack,
  onNew,
}: {
  run: HistoryRun;
  script: string;
  onBack: () => void;
  onNew: () => void;
}) {
  const [tab, setTab] = useState<"html" | "transcript" | "artifacts" | "video">("html");
  const hasHtml = Boolean(run.artifacts["demo-script-html"]);
  const hasVideo = Boolean(run.artifacts.video);
  const artifactLabels: Record<string, string> = {
    "demo-script": "Demo script (.md)",
    "demo-script-html": "Demo script (.html)",
    "talking-script-json": "Talking script (.json)",
    "talking-script": "Talking script (.md)",
    video: "Demo video (.mp4)",
  };
  const artifactUrlFor = (name: string) => historyArtifactUrl(run, name);

  return (
    <section className="mx-auto max-w-5xl pt-8">
      <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <div className="eyebrow">
            <Check size={14} /> SAVED RUN
          </div>
          <h1 className="hero-title">{run.app_slug} demo.</h1>
          <p className="hero-copy">
            Run {run.run_id} completed {run.run_timestamp}.
          </p>
        </div>
        <div className="flex gap-3">
          <button className="secondary-button" onClick={onBack}>
            Back to history
          </button>
          <a
            className="secondary-button"
            href={historyDownloadUrl(run)}
            download={`pitchpilot-${run.run_id}.zip`}
          >
            <Download size={16} /> Download all
          </a>
          <button className="secondary-button" onClick={onNew}>
            New run <Sparkles size={16} />
          </button>
        </div>
      </div>
      <div className="surface overflow-hidden">
        <div className="result-tabs">
          <button
            className={`tab ${tab === "html" ? "active" : ""}`}
            onClick={() => setTab("html")}
            disabled={!hasHtml}
          >
            HTML Preview
          </button>
          <button
            className={`tab ${tab === "transcript" ? "active" : ""}`}
            onClick={() => setTab("transcript")}
          >
            Transcript
          </button>
          <button
            className={`tab ${tab === "artifacts" ? "active" : ""}`}
            onClick={() => setTab("artifacts")}
          >
            <FileCheck size={15} /> Artifacts
          </button>
          {hasVideo && (
            <button
              className={`tab ${tab === "video" ? "active" : ""}`}
              onClick={() => setTab("video")}
            >
              <Video size={15} /> Video
            </button>
          )}
        </div>
        {tab === "html" && hasHtml && (
          <div className="html-inline">
            <div className="document-toolbar">
              <span>
                <FileText size={15} /> Generated demo-script.html
              </span>
              <a
                href={artifactUrlFor("demo-script-html")}
                target="_blank"
                rel="noreferrer"
              >
                Open in new tab <ArrowRight size={14} />
              </a>
            </div>
            <iframe
              title="Saved presenter script with screenshots"
              src={artifactUrlFor("demo-script-html")}
            />
          </div>
        )}
        {tab !== "html" && (
          <div className="p-6 sm:p-10">
            {tab === "transcript" && (
              <article className="prose max-w-3xl">
                <ReactMarkdown>{script || "Loading transcript..."}</ReactMarkdown>
              </article>
            )}
            {tab === "video" && hasVideo && (
              <div className="video-panel max-w-3xl">
                <div className="video-label">
                  <Video size={15} /> Preview
                </div>
                <video className="video" controls src={artifactUrlFor("video")} />
                <a
                  className="primary-button mt-4"
                  href={artifactUrlFor("video")}
                  download="demo-video.mp4"
                >
                  Download video <ArrowRight size={16} />
                </a>
              </div>
            )}
            {tab === "artifacts" && (
              <div className="artifact-panel">
                <div className="artifact-list-heading">
                  <FileCheck size={16} /> Files generated for this run
                </div>
                <div className="artifact-download-grid">
                  {Object.entries(run.artifacts)
                    .filter(([name]) => artifactLabels[name])
                    .map(([name, path]) => (
                      <a
                        className="artifact-download"
                        href={artifactUrlFor(name)}
                        target="_blank"
                        rel="noreferrer"
                        key={name}
                      >
                        <FileText size={15} />
                        <span>{artifactLabels[name]}</span>
                        <ArrowRight size={14} />
                        <span className="artifact-path">
                          {path.split(/[\\/]/).pop()}
                        </span>
                      </a>
                    ))}
                </div>
                <p className="screenshot-summary">
                  <FileCheck size={14} /> {run.screenshot_count ?? run.screenshots.length} screenshots captured
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function Progress({ job, onBack }: { job: JobSnapshot; onBack: () => void }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, []);
  const failed = job.status === "failed";
  const currentIndex = steps.indexOf(job.stage as (typeof steps)[number]);
  const visibleSteps = job.make_video ? steps : steps.slice(0, 2);
  const totalSteps = visibleSteps.length;
  const progress =
    job.progress ||
    (job.status === "running" && job.stage === "exploring" ? 10 : 0);
  const hasScript = Boolean(job.artifacts["talking-script"]);
  const hasVideo = Boolean(job.artifacts.video);
  const preparing = job.stage === "queued";
  const stageLabel = failed
    ? "Run failed"
    : job.status === "completed"
      ? "All requested files are ready"
      : preparing
        ? "Preparing the worker"
        : `Stage ${Math.min(currentIndex + 1, totalSteps)} of ${totalSteps}`;
  const activity = failed
    ? "Run failed"
    : job.status === "completed"
      ? "All requested files are ready"
      : preparing
        ? "Starting the run..."
        : job.message ||
          (job.stage === "exploring"
            ? "Exploring the app - Chromium is visiting pages"
            : "Working now");
  return (
    <section className="mx-auto max-w-3xl pt-8">
      <div className="mb-10">
        <div className="eyebrow">
          <Sparkles size={14} /> LIVE RUN
        </div>
        <h1 className="hero-title max-w-2xl">Your demo is taking shape.</h1>
        <p className="hero-copy">
          PitchPilot is working in the background. This page updates whenever a
          stage or artifact is ready.
        </p>
      </div>
      <div className="surface p-6 sm:p-10">
        <div className="progress-heading">
          <div>
            <p className="field-label">Estimated progress</p>
            <div className="progress-number">
              {progress}
              <span>%</span>
            </div>
            <p className="progress-note">{stageLabel}</p>
          </div>
          <div className="live-readout">
            <span className={`live-dot ${failed ? "stopped" : ""}`} />
            {failed
              ? "Stopped"
              : job.status === "completed"
                ? "Ready"
                : "Live processing"}
            <span className="elapsed">
              <CircleDot size={13} />
              {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
            </span>
          </div>
        </div>
        <p className="run-time">
          Run started {job.run_timestamp || job.started_at || "just now"}
        </p>
        <div
          className={`progress-track ${!failed && job.status !== "completed" ? "indeterminate" : ""}`}
        >
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="run-meta">
          <div>
            <p className="field-label">Current activity</p>
            <p className="current-activity">{activity}</p>
          </div>
          <span
            className={`status ${failed ? "status-error" : job.status === "completed" ? "status-success" : "status-active"}`}
          >
            {failed
              ? "Needs attention"
              : job.status === "completed"
                ? "Complete"
                : "In progress"}
          </span>
        </div>
        <div className="stepper">
          {visibleSteps.map((step, index) => {
            const done =
              !failed && (job.stage === "completed" || currentIndex > index);
            const active = !failed && currentIndex === index;
            return (
              <div className="step" key={step}>
                <div
                  className={`step-dot ${done ? "done" : active ? "active" : failed && currentIndex === index ? "failed" : ""}`}
                >
                  {done ? (
                    <Check size={16} />
                  ) : active ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    index + 1
                  )}
                </div>
                <div>
                  <p className="step-title">
                    {step === "exploring"
                      ? "Explore"
                      : step === "narrating"
                        ? "Narrate"
                        : "Render"}
                  </p>
                  <p className="muted">
                    {active
                      ? job.message || "Working now"
                      : done
                        ? "Finished"
                        : preparing && index === 0
                          ? "Starting next"
                          : "Waiting"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
        <div className="artifact-list">
          <div className="artifact-list-heading">
            <FileCheck size={16} /> Generated files
          </div>
          <ArtifactStatus
            label="Demo script + screenshots"
            ready={currentIndex > 0 || job.status === "completed"}
            active={job.stage === "exploring"}
          />
          <ArtifactStatus
            label="Talking script (.md)"
            ready={hasScript || job.status === "completed"}
            active={job.stage === "narrating"}
          />
          <ArtifactStatus
            label="Demo video (.mp4)"
            ready={hasVideo}
            active={job.stage === "rendering"}
            optional={!job.make_video}
          />
        </div>
        {failed && (
          <div className="error-box mt-8">
            <p className="field-label text-rose-700 dark:text-rose-300">
              Run failed
            </p>
            <p className="mt-1 text-sm">{job.error}</p>
          </div>
        )}
        <button className="secondary-button mt-10" onClick={onBack}>
          {failed ? "Start over" : "Cancel run"}
        </button>
      </div>
    </section>
  );
}

function ArtifactStatus({
  label,
  ready,
  active,
  optional = false,
}: {
  label: string;
  ready: boolean;
  active: boolean;
  optional?: boolean;
}) {
  return (
    <div className="artifact-row">
      <span
        className={`artifact-icon ${ready ? "ready" : active ? "building" : ""}`}
      >
        {ready ? (
          <Check size={14} />
        ) : active ? (
          <LoaderCircle className="spin" size={14} />
        ) : (
          <FileText size={14} />
        )}
      </span>
      <span>{label}</span>
      <span className="artifact-state">
        {ready
          ? "Ready"
          : active
            ? "Generating"
            : optional
              ? "Not selected"
              : "Waiting"}
      </span>
    </div>
  );
}

function Result({
  job,
  script,
  onNew,
}: {
  job: JobSnapshot;
  script: string;
  onNew: () => void;
}) {
  const [tab, setTab] = useState<"html" | "transcript" | "artifacts" | "video">(
    "html",
  );
  const artifactLabels: Record<string, string> = {
    "demo-script": "Demo script (.md)",
    "demo-script-html": "Demo script (.html)",
    "latest-html": "Standalone latest (.html)",
    "talking-script-json": "Talking script (.json)",
    "talking-script": "Talking script (.md)",
  };
  const screenshotCount = job.screenshots?.length ?? 0;
  const hasHtml = Boolean(job.artifacts["demo-script-html"]);
  return (
    <section className="mx-auto max-w-5xl pt-8">
      <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <div className="eyebrow">
            <Check size={14} /> RUN COMPLETE
          </div>
          <h1 className="hero-title">Your demo is ready.</h1>
          <p className="hero-copy">
            Open the generated presenter document, read the transcript, or
            download the source artifacts.
          </p>
        </div>
        <div className="flex gap-3">
          <a
            className="secondary-button"
            href={jobDownloadUrl(job.job_id)}
            download="pitchpilot-artifacts.zip"
          >
            <Download size={16} /> Download all
          </a>
          <button className="secondary-button" onClick={onNew}>
            New run <Sparkles size={16} />
          </button>
        </div>
      </div>
      <div className="surface overflow-hidden">
        <div className="result-tabs">
          <button
            className={`tab ${tab === "html" ? "active" : ""}`}
            onClick={() => setTab("html")}
            disabled={!hasHtml}
          >
            HTML Preview
          </button>
          <button
            className={`tab ${tab === "transcript" ? "active" : ""}`}
            onClick={() => setTab("transcript")}
          >
            Transcript
          </button>
          <button
            className={`tab ${tab === "artifacts" ? "active" : ""}`}
            onClick={() => setTab("artifacts")}
          >
            <FileCheck size={15} /> Artifacts
          </button>
          {job.make_video && (
            <button
              className={`tab ${tab === "video" ? "active" : ""}`}
              onClick={() => setTab("video")}
            >
              <Video size={15} /> Video
            </button>
          )}
        </div>
        {tab === "html" && hasHtml && (
          <div className="html-inline">
            <div className="document-toolbar">
              <span>
                <FileText size={15} /> Generated demo-script.html
              </span>
              <a
                href={artifactUrl(job.job_id, "demo-script-html")}
                target="_blank"
                rel="noreferrer"
              >
                Open in new tab <ArrowRight size={14} />
              </a>
            </div>
            <iframe
              title="Generated presenter script with screenshots"
              src={artifactUrl(job.job_id, "demo-script-html")}
            />
          </div>
        )}{" "}
        {tab !== "html" && (
          <div className="p-6 sm:p-10">
            {tab === "video" && job.make_video && (
              <div className="video-panel max-w-3xl">
                <div className="video-label">
                  <Video size={15} /> Preview
                </div>
                <video className="video" controls src={videoUrl(job.job_id)} />
                <a
                  className="primary-button mt-4"
                  href={videoUrl(job.job_id)}
                  download="demo-video.mp4"
                >
                  Download video <ArrowRight size={16} />
                </a>
              </div>
            )}
            {tab === "transcript" && (
              <article className="prose max-w-3xl">
                <ReactMarkdown>
                  {script || "Loading transcript..."}
                </ReactMarkdown>
              </article>
            )}
            {tab === "artifacts" && (
              <ArtifactPanel
                job={job}
                labels={artifactLabels}
                screenshotCount={screenshotCount}
              />
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function ArtifactPanel({
  job,
  labels,
  screenshotCount,
}: {
  job: JobSnapshot;
  labels: Record<string, string>;
  screenshotCount: number;
}) {
  return (
    <div className="artifact-panel">
      <div className="artifact-list-heading">
        <FileCheck size={16} /> Files generated for this run
      </div>
      <div className="artifact-download-grid">
        {Object.entries(job.artifacts)
          .filter(([name]) => labels[name])
          .map(([name, path]) => (
            <a
              className="artifact-download"
              href={artifactUrl(job.job_id, name)}
              target="_blank"
              rel="noreferrer"
              key={name}
            >
              <FileText size={15} />
              <span>{labels[name]}</span>
              <ArrowRight size={14} />
              <span className="artifact-path">{path.split(/[\\/]/).pop()}</span>
            </a>
          ))}
      </div>
      <p className="screenshot-summary">
        <FileCheck size={14} /> {screenshotCount} screenshot
        {screenshotCount === 1 ? "" : "s"} captured
      </p>
    </div>
  );
}
