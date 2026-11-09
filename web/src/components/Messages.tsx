import { ChevronDown, Download, FileText, Play, RotateCcw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { useNow } from "../hooks";
import type { Job, JobEvent } from "../types";
import { fileIcon } from "./Composer";
import { ActivityLog, PhaseStrip } from "./Progress";
import { SlideViewer } from "./SlideViewer";
import { cx, formatBytes, formatDuration } from "./ui";

export function UserMessage({ job }: { job: Job }) {
  const text = job.parent_id ? job.feedback ?? "" : job.brief;
  const long = text.length > 900;
  const [open, setOpen] = useState(false);
  const files = job.files ?? [];
  return (
    <div className="animate-rise flex w-full flex-col items-end gap-2">
      {files.length > 0 && (
        <div className="flex max-w-[85%] flex-wrap justify-end gap-1.5">
          {files.slice(0, 12).map((f) => {
            const Icon = fileIcon(f.name);
            return (
              <span
                key={f.name}
                className="inline-flex max-w-[220px] items-center gap-1.5 rounded-lg border border-line bg-white px-2 py-1 text-xs text-ink-2"
                title={f.name}
              >
                <Icon className="size-3.5 shrink-0 text-mute" />
                <span className="truncate">{f.name.split("/").pop()}</span>
                <span className="shrink-0 text-faint">{formatBytes(f.bytes)}</span>
              </span>
            );
          })}
          {files.length > 12 && (
            <span className="rounded-lg border border-line bg-white px-2 py-1 text-xs text-mute">
              +{files.length - 12} more
            </span>
          )}
        </div>
      )}
      {text && (
        <div className="max-w-[85%] rounded-xl border border-line bg-canvas px-3.5 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap text-ink">
          {long && !open ? `${text.slice(0, 900).trimEnd()}…` : text}
          {(job.brief_chars ?? 0) > text.length && open && !job.parent_id && (
            <span className="text-mute"> … ({(job.brief_chars ?? 0).toLocaleString()} characters in total)</span>
          )}
          {long && (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              className="mt-1 block text-xs font-medium text-brand hover:text-brand-700"
            >
              {open ? "Show less" : "Show all"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Kicker({ children }: { children: React.ReactNode }) {
  return <p className="mb-2 text-[10px] font-medium tracking-[0.14em] text-brand uppercase">{children}</p>;
}

function Pill({
  children,
  onClick,
  href,
  primary,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  href?: string;
  primary?: boolean;
}) {
  const cls = cx(
    "inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[12.5px] font-medium transition-colors",
    primary
      ? "bg-brand text-white hover:bg-brand-600"
      : "border border-line bg-white text-ink hover:border-line-strong",
  );
  return href ? (
    <a href={href} className={cls}>
      {children}
    </a>
  ) : (
    <button type="button" onClick={onClick} className={cls}>
      {children}
    </button>
  );
}

export function AssistantMessage({
  job,
  events,
  latest,
  onOpenPanel,
  onRetry,
}: {
  job: Job;
  events: JobEvent[];
  latest: boolean;
  onOpenPanel: (tab: "report" | "draft" | "activity") => void;
  onRetry: () => void;
}) {
  const live = job.status === "running" || job.status === "queued";
  const now = useNow(live);
  const [showLog, setShowLog] = useState(false);
  const [present, setPresent] = useState(false);
  const r = job.result;
  const label = job.version > 1 ? `Version ${job.version}` : "Deck";

  if (live) {
    const lastLine = [...events].reverse().find((e) => e.type === "log" && (e.kind === "agent" || e.kind === "ok" || e.kind === "info"));
    const elapsed = now - (job.started_at ?? job.created_at);
    return (
      <div className="animate-rise w-full">
        <Kicker>{label}</Kicker>
        <div className="rounded-xl border border-line bg-white px-4 py-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <PhaseStrip stages={job.stages} />
            <span className="text-[11px] text-mute tabular-nums">
              {job.status === "queued" ? "Queued" : formatDuration(elapsed)}
            </span>
          </div>
          <p className="mt-2.5 min-h-[1.3em] text-[13px] leading-snug text-ink-2">
            {job.status === "queued" ? "Waiting for a free worker." : lastLine?.text ?? "Reading your input."}
          </p>
          <button
            type="button"
            onClick={() => setShowLog((s) => !s)}
            className="mt-2 inline-flex items-center gap-1 text-xs text-mute hover:text-ink"
          >
            {showLog ? "Hide" : "Show"} activity
            <ChevronDown className={cx("size-3 transition-transform", showLog && "rotate-180")} />
          </button>
          {showLog && (
            <ActivityLog events={events} stages={job.stages} live className="mt-2 max-h-72 border-t border-line pt-1" />
          )}
        </div>
      </div>
    );
  }

  if (!r) {
    const failed = job.status === "failed";
    return (
      <div className="animate-rise w-full">
        <Kicker>{label}</Kicker>
        <p className={cx("text-[14px] leading-relaxed", failed ? "text-signal" : "text-mute")}>
          {failed ? job.error || "The deck could not be built." : "Stopped before the deck was finished."}
        </p>
        {latest && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Pill onClick={onRetry}>
              <RotateCcw className="size-3.5" /> Run again
            </Pill>
            <Pill onClick={() => onOpenPanel("activity")}>Activity</Pill>
          </div>
        )}
      </div>
    );
  }

  const rep = r.report;
  const summary = job.parent_id ? rep.stage_summaries.draft : rep.stage_summaries.draft || rep.stage_summaries.plan;
  return (
    <div className="animate-rise w-full">
      <Kicker>{label}</Kicker>
      <h3 className="font-display text-[19px] leading-snug font-semibold tracking-tight text-ink">{rep.title}</h3>
      <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-mute">
        <span>{r.slide_count} slides</span>
        <span>·</span>
        <span>built in {formatDuration(r.duration)}</span>
        <span>·</span>
        <span className={cx("inline-flex items-center gap-1", rep.verify.result === "PASS" ? "text-ok" : "text-signal")}>
          <ShieldCheck className="size-3.5" />
          {rep.verify.result === "PASS" ? `passes ${rep.verify.passed}/23 guide checks` : "verify failed"}
        </span>
      </p>
      {r.unchanged && (
        <p className="mt-3 rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-ink-2">
          Nothing changed in this version. The slides are the same as version {job.version - 1}.
        </p>
      )}
      {summary && <p className="mt-3 text-[14px] leading-relaxed text-ink-2">{summary}</p>}
      {r.overrides && r.overrides.total > 0 && (
        <p className="mt-2 text-[13px] leading-relaxed text-mute">
          {r.overrides.rules
            .map((x) => {
              const st = [x.italic && "italic", x.bold && "bold", x.underline && "underlined"].filter(Boolean).join(", ");
              return `"${x.text}" in ${st}`;
            })
            .join("; ")}{" "}
          ({r.overrides.total} place{r.overrides.total === 1 ? "" : "s"}). This is an exception you asked for: the
          amasol style guide uses no italics or underline.
        </p>
      )}

      <div className="mt-4">
        <SlideViewer
          slides={r.slides.map((s) => api.fileUrl(job.id, s))}
          hd={(r.slides_hd ?? []).map((s) => api.fileUrl(job.id, s))}
          meta={rep.slides}
          keyboard={latest}
          present={present}
          setPresent={setPresent}
        />
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        <Pill primary onClick={() => setPresent(true)}>
          <Play className="size-3 fill-current" /> Present
        </Pill>
        <Pill href={api.fileUrl(job.id, r.pptx, true)}>
          <Download className="size-3.5" /> PowerPoint
        </Pill>
        {r.pdf && (
          <Pill href={api.fileUrl(job.id, r.pdf, true)}>
            <FileText className="size-3.5" /> PDF
          </Pill>
        )}
        <Pill onClick={() => onOpenPanel("report")}>Report</Pill>
        <Pill onClick={() => onOpenPanel("draft")}>Draft</Pill>
        <Pill onClick={() => onOpenPanel("activity")}>Activity</Pill>
      </div>
    </div>
  );
}
