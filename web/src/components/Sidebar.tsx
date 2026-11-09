import { Trash2 } from "lucide-react";
import type { JobSummary } from "../types";
import { cx, timeAgo } from "./ui";

export interface ThreadSummary {
  root: string;
  latest: JobSummary;
  first: JobSummary;
  versions: number;
  busy: boolean;
}

/** One entry per deck thread (root job), newest activity first. */
export function threadsFrom(jobs: JobSummary[]): ThreadSummary[] {
  const by = new Map<string, JobSummary[]>();
  for (const j of jobs) by.set(j.root_id, [...(by.get(j.root_id) ?? []), j]);
  return [...by.entries()]
    .map(([root, vs]) => {
      vs.sort((a, b) => a.version - b.version);
      return {
        root,
        first: vs[0],
        latest: vs[vs.length - 1],
        versions: vs.length,
        busy: vs.some((v) => v.status === "running" || v.status === "queued"),
      };
    })
    .sort((a, b) => b.latest.created_at - a.latest.created_at);
}

const STATUS: Record<string, string> = {
  done: "Ready",
  running: "Building",
  queued: "Queued",
  failed: "Failed",
  cancelled: "Stopped",
};

export function Sidebar({
  threads,
  current,
  onOpen,
  onNew,
  onDelete,
}: {
  threads: ThreadSummary[];
  current: string | null;
  onOpen: (root: string) => void;
  onNew: () => void;
  onDelete: (t: ThreadSummary) => void;
}) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-canvas/70 md:flex">
      <div className="flex items-center justify-between border-b border-line px-3 py-3">
        <span className="text-[10px] font-medium tracking-[0.16em] text-mute uppercase">Decks</span>
        <button
          type="button"
          onClick={onNew}
          className="text-[11px] font-medium tracking-[0.08em] text-brand uppercase hover:text-brand-700"
        >
          New
        </button>
      </div>
      <div className="scroll-thin flex flex-1 flex-col gap-2 overflow-y-auto p-2">
        {threads.length === 0 && <p className="px-2 py-4 text-xs text-mute">Your decks show up here.</p>}
        {threads.map((t) => (
          <div key={t.root} className="group relative">
            <button
              type="button"
              onClick={() => onOpen(t.root)}
              className={cx(
                "w-full rounded-lg border bg-white px-3 py-2.5 text-left transition-colors",
                t.root === current ? "border-brand ring-1 ring-brand/20" : "border-line hover:border-line-strong",
              )}
            >
              <p className="line-clamp-2 pr-4 text-[13px] leading-snug font-medium text-ink">{t.latest.title}</p>
              <p className="mt-1 truncate text-[11px] text-mute">{t.first.snippet}</p>
              <p className="mt-1.5 flex items-center gap-1.5 text-[10px] tracking-[0.08em] text-mute uppercase">
                <span
                  className={cx(
                    "size-1.5 rounded-full",
                    t.busy ? "animate-pulse bg-brand" : t.latest.status === "failed" ? "bg-signal" : "bg-ok",
                    t.latest.status === "cancelled" && !t.busy && "bg-line-strong",
                  )}
                />
                {STATUS[t.latest.status]}
                {t.latest.slides ? ` · ${t.latest.slides} slides` : ""}
                {t.versions > 1 ? ` · v${t.latest.version}` : ""}
                <span className="ml-auto normal-case tracking-normal">{timeAgo(t.latest.created_at)}</span>
              </p>
            </button>
            {!t.busy && (
              <button
                type="button"
                aria-label="Delete deck"
                title="Delete this deck and its versions"
                onClick={() => {
                  if (confirm(`Delete "${t.latest.title}" and all its versions?`)) onDelete(t);
                }}
                className="absolute top-2 right-2 rounded p-1 text-faint opacity-0 group-hover:opacity-100 hover:bg-canvas hover:text-signal"
              >
                <Trash2 className="size-3.5" />
              </button>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
