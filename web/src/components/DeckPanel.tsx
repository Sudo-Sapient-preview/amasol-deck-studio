import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useJobEvents } from "../hooks";
import type { Job } from "../types";
import { ActivityLog } from "./Progress";
import { ReportView } from "./ReportView";
import { cx } from "./ui";

export type PanelTab = "report" | "draft" | "activity";

/** Right-hand panel for one version: its report, draft or activity log. */
export function DeckPanel({
  job,
  tab,
  setTab,
  onClose,
}: {
  job: Job;
  tab: PanelTab;
  setTab: (t: PanelTab) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const events = useJobEvents(tab === "activity" ? job.id : null);

  useEffect(() => setDraft(null), [job.id]);
  useEffect(() => {
    if (tab === "draft" && draft === null) api.draft(job.id).then(setDraft, () => setDraft(""));
  }, [tab, draft, job.id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tabs: [PanelTab, string][] = [
    ["report", "Report"],
    ["draft", "Draft"],
    ["activity", "Activity"],
  ];

  return (
    <>
      <div className="fixed inset-0 z-30 bg-ink/20 lg:hidden" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[460px] flex-col border-l border-line bg-white shadow-pop lg:static lg:z-auto lg:w-[440px] lg:shadow-none">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 pt-4 pb-0">
          <div className="min-w-0">
            <p className="text-[10px] font-medium tracking-[0.14em] text-mute uppercase">
              {job.version > 1 ? `Version ${job.version}` : "Deck"}
            </p>
            <h2 className="mt-0.5 truncate font-display text-[17px] font-semibold tracking-tight text-ink">
              {job.result?.report.title || job.title}
            </h2>
            <div className="mt-2 flex gap-1">
              {tabs.map(([k, l]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setTab(k)}
                  disabled={k !== "activity" && !job.result}
                  className={cx(
                    "-mb-px border-b-2 px-2 py-2 text-[13px] font-medium transition-colors disabled:text-faint",
                    tab === k ? "border-brand text-ink" : "border-transparent text-mute hover:text-ink",
                  )}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close panel"
            className="rounded-md p-1.5 text-mute hover:bg-canvas hover:text-ink"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="scroll-thin flex-1 overflow-y-auto px-5 py-5">
          {tab === "report" && job.result && <ReportView report={job.result.report} />}
          {tab === "draft" && (
            <>
              <p className="mb-3 text-xs text-mute">
                The standard draft every slide is built from. Notes and flags go into the speaker notes.
              </p>
              <pre className="rounded-lg border border-line bg-canvas p-4 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-2">
                {draft ?? "Loading…"}
              </pre>
            </>
          )}
          {tab === "activity" && (
            <ActivityLog
              events={events}
              stages={job.stages}
              live={job.status === "running" || job.status === "queued"}
            />
          )}
        </div>
      </aside>
    </>
  );
}
