import {
  Check,
  CircleCheck,
  CircleX,
  Info,
  LoaderCircle,
  MessageSquare,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import { useEffect, useRef } from "react";
import type { JobEvent, Stage } from "../types";
import { cx } from "./ui";

const SHORT: Record<string, string> = {
  ingest: "Read",
  draft: "Storyline",
  plan: "Visuals",
  build: "Build",
  review: "Review",
};

/** Read · Storyline · Visuals · Build · Review, the running one pulsing. */
export function PhaseStrip({ stages }: { stages: Stage[] }) {
  return (
    <ol className="flex flex-wrap items-center">
      {stages.map((s, i) => (
        <li key={s.key} className="flex items-center">
          {i > 0 && <span className="mx-2 h-px w-4 bg-line-strong" />}
          <span
            className={cx(
              "inline-flex items-center gap-1 text-[10px] tracking-[0.16em] uppercase",
              s.status === "done" && "text-ink",
              s.status === "running" && "animate-pulse font-bold text-brand",
              s.status === "failed" && "font-bold text-signal",
              (s.status === "pending" || s.status === "skipped") && "text-faint",
            )}
          >
            {s.status === "done" && <Check className="size-3" strokeWidth={3} />}
            {SHORT[s.key] ?? s.label}
          </span>
        </li>
      ))}
    </ol>
  );
}

const KIND = {
  info: { icon: Info, cls: "text-brand" },
  agent: { icon: MessageSquare, cls: "text-ink-2" },
  tool: { icon: Wrench, cls: "text-faint" },
  ok: { icon: CircleCheck, cls: "text-ok" },
  warn: { icon: TriangleAlert, cls: "text-warn" },
  error: { icon: CircleX, cls: "text-signal" },
  note: { icon: Info, cls: "text-mute" },
} as const;

export function ActivityLog({
  events,
  stages,
  live,
  className,
}: {
  events: JobEvent[];
  stages: Stage[];
  live: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const label = Object.fromEntries(stages.map((s) => [s.key, s.label]));
  const t0 = events[0]?.t ?? 0;
  const rows = events.filter(
    (e) => e.type === "log" || (e.type === "stage" && (e.status === "running" || e.status === "failed")),
  );

  return (
    <div
      ref={ref}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      }}
      className={cx("scroll-thin overflow-y-auto", className)}
    >
      <ul className="space-y-0.5 py-1">
        {rows.map((e) => {
          if (e.type === "stage") {
            return (
              <li key={e.seq} className="flex items-center gap-2 px-1 pt-3 pb-1 first:pt-1">
                <span className="text-[11px] font-semibold tracking-wide text-mute uppercase">
                  {label[e.key ?? ""] ?? e.key}
                  {e.status === "failed" ? " · failed" : ""}
                </span>
                <span className="h-px flex-1 bg-line" />
              </li>
            );
          }
          const k = KIND[e.kind ?? "note"] ?? KIND.note;
          const Icon = k.icon;
          return (
            <li key={e.seq} className="animate-rise flex gap-2.5 rounded-md px-1 py-1 hover:bg-canvas">
              <Icon className={cx("mt-0.5 size-3.5 shrink-0", k.cls)} />
              <span
                className={cx(
                  "min-w-0 flex-1 text-[13px] leading-snug break-words",
                  e.kind === "agent" ? "text-ink" : e.kind === "tool" ? "text-mute" : "text-ink-2",
                  e.kind === "error" && "text-signal",
                )}
              >
                {e.text}
              </span>
              <span className="shrink-0 pt-0.5 text-[11px] text-faint tabular-nums">
                {formatClock(e.t - t0)}
              </span>
            </li>
          );
        })}
        {live && (
          <li className="flex items-center gap-2.5 px-1 py-1 text-[13px] text-mute">
            <LoaderCircle className="size-3.5 animate-spin text-brand" />
            Working
          </li>
        )}
      </ul>
    </div>
  );
}

function formatClock(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
