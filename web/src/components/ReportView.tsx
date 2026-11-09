import { CircleCheck, CircleX, ShieldCheck, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Report } from "../types";
import { Badge, cx } from "./ui";

const STAGE_LABEL: Record<string, string> = {
  ingest: "Reading inputs",
  draft: "Storyline",
  plan: "Visual plan",
  build: "Build",
  review: "Visual review",
};

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-line py-5 first:border-t-0 first:pt-0">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold text-ink">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function List({ items, tone }: { items: string[]; tone?: "warn" }) {
  if (!items.length) return <p className="text-[13px] text-mute">None</p>;
  return (
    <ul className="space-y-1.5">
      {items.map((t, i) => (
        <li key={i} className="flex gap-2 text-[13px] leading-snug text-ink-2">
          <span className={cx("mt-1.5 size-1.5 shrink-0 rounded-full", tone === "warn" ? "bg-warn" : "bg-line-strong")} />
          <span className="min-w-0 break-words">{t}</span>
        </li>
      ))}
    </ul>
  );
}

export function ReportView({ report }: { report: Report }) {
  const [showChecks, setShowChecks] = useState(false);
  const v = report.verify;
  const pass = v.result === "PASS";
  const content = report.slides.filter((s) => s.kind === "content");

  return (
    <div>
      <Section title="Verification">
        <div
          className={cx(
            "flex items-center gap-3 rounded-lg px-4 py-3 ring-1 ring-inset",
            pass ? "bg-ok-50 ring-ok/15" : "bg-signal-50 ring-signal/15",
          )}
        >
          {pass ? <ShieldCheck className="size-5 text-ok" /> : <CircleX className="size-5 text-signal" />}
          <div className="min-w-0 flex-1">
            <p className={cx("text-sm font-semibold", pass ? "text-ok" : "text-signal")}>
              {pass ? "Passes the style guide checks" : "Verification failed"}
            </p>
            <p className="text-xs text-ink-2">
              {v.passed ?? "?"} of 23 checks passed{v.failed ? `, ${v.failed} failed` : ""}
              {v.skipped ? `, ${v.skipped} skipped` : ""} · scripts/verify_deck.py --strict
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowChecks((x) => !x)}
            className="text-xs font-medium text-brand hover:text-brand-700"
          >
            {showChecks ? "Hide checks" : "Show checks"}
          </button>
        </div>
        {v.notes.length > 0 && (
          <div className="mt-3">
            <p className="mb-1.5 text-xs font-medium text-mute">Recorded deviations (waivers and short-pitch skips)</p>
            <List items={v.notes} tone="warn" />
          </div>
        )}
        {showChecks && (
          <ul className="mt-3 space-y-1 rounded-lg border border-line p-3">
            {v.lines.map((l, i) => {
              const ok = l.startsWith("PASS");
              return (
                <li key={i} className="flex gap-2 text-xs leading-snug text-ink-2">
                  {ok ? (
                    <CircleCheck className="mt-px size-3.5 shrink-0 text-ok" />
                  ) : (
                    <TriangleAlert className="mt-px size-3.5 shrink-0 text-warn" />
                  )}
                  <span>{l.replace(/^(PASS|FAIL|SKIP)\s+/, "")}</span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section
        title="Input"
        aside={<Badge tone="brand">{report.input_type || "unknown"}</Badge>}
      >
        <p className="mb-3 text-[13px] leading-relaxed text-ink-2">{report.input_reason}</p>
        <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 text-[13px]">
          <dt className="text-mute">Audience</dt>
          <dd className="text-ink">{report.audience || "-"}</dd>
          <dt className="text-mute">Goal</dt>
          <dd className="text-ink">{report.goal || "-"}</dd>
          <dt className="text-mute">Language</dt>
          <dd className="text-ink">{report.language === "de" ? "German" : "English"}</dd>
        </dl>
      </Section>

      <Section
        title="Assumptions and open items"
        aside={
          report.assumed.length + report.flagged.length > 0 ? (
            <Badge tone="warn">{report.assumed.length + report.flagged.length} to confirm</Badge>
          ) : undefined
        }
      >
        <div className="space-y-4">
          <div>
            <p className="mb-1.5 text-xs font-medium text-mute">Header fields filled in by assumption</p>
            <List items={report.assumed} tone="warn" />
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-mute">
              Flagged content (assumption, needs-source, to-be-filled)
            </p>
            <List items={report.flagged} tone="warn" />
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-mute">Edits to your content</p>
            <List items={report.edits} />
          </div>
        </div>
      </Section>

      <Section
        title="Visual plan"
        aside={
          <span className="text-xs text-mute">
            {report.plan.infographics} infographic{report.plan.infographics === 1 ? "" : "s"} of max{" "}
            {report.plan.cap ?? "?"}
            {report.plan.short_pitch ? " · short pitch" : ""}
          </span>
        }
      >
        <div className="overflow-hidden rounded-lg border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-canvas text-xs text-mute">
              <tr>
                <th className="w-10 px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Slide</th>
                <th className="px-3 py-2 font-medium">Visual and layout</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {report.slides.map((s) => (
                <tr key={s.n} className="align-top">
                  <td className="px-3 py-2 text-mute tabular-nums">{s.n}</td>
                  <td className="px-3 py-2">
                    <p className={cx("text-ink", s.kind !== "content" && "text-mute")}>
                      {s.kind === "content" ? s.title : `${s.kind[0].toUpperCase()}${s.kind.slice(1)}${s.title && s.kind !== "agenda" ? `: ${s.title}` : ""}`}
                    </p>
                    {s.plan_reason && <p className="mt-0.5 text-xs text-mute">{s.plan_reason}</p>}
                  </td>
                  <td className="px-3 py-2">
                    {s.kind === "content" && <p className="font-medium text-ink">{s.visual}</p>}
                    <p className="text-xs text-mute">{s.layout}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(report.plan.cut.length > 0 || report.plan.excluded.length > 0 || report.plan.no_chart.length > 0) && (
          <div className="mt-4 space-y-3">
            {report.plan.cut.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-mute">Infographics cut to stay under the cap</p>
                <List items={report.plan.cut.map((c) => `${c.id}: ${c.wanted} → ${c.now}. ${c.reason ?? ""}`)} />
              </div>
            )}
            {report.plan.no_chart.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-mute">No chart, and why</p>
                <List items={report.plan.no_chart.map((c) => `${c.source_ref}: ${c.reason}`)} />
              </div>
            )}
            {report.plan.excluded.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-mute">Lines left out of the deck</p>
                <List items={report.plan.excluded.map((c) => `"${c.quote}": ${c.reason}`)} />
              </div>
            )}
          </div>
        )}
        <p className="mt-3 text-xs text-mute">{content.length} content slides, {report.slides.length} slides in total.</p>
      </Section>

      <Section title="Notes from each stage">
        <dl className="space-y-3">
          {Object.entries(report.stage_summaries)
            .filter(([, t]) => t)
            .map(([k, t]) => (
              <div key={k}>
                <dt className="text-xs font-medium text-mute">{STAGE_LABEL[k] ?? k}</dt>
                <dd className="mt-0.5 text-[13px] leading-relaxed text-ink-2">{t}</dd>
              </div>
            ))}
        </dl>
      </Section>

      {report.warnings.length > 0 && (
        <Section title="Input warnings">
          <List items={report.warnings} tone="warn" />
        </Section>
      )}

      <Section title="Fonts">
        <p className="text-[13px] text-ink-2">{report.font_note}</p>
      </Section>
    </div>
  );
}
