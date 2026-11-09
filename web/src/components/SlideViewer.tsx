import { ChevronLeft, ChevronRight, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ReportSlide } from "../types";
import { Presenter } from "./Presenter";
import { Badge, cx } from "./ui";

const VISUAL_LABEL: Record<string, string> = {
  icon_set: "Icon rows",
  big_number: "Key number",
  key_slide: "Key slide",
  quote: "Quote",
  chart: "Chart",
  table: "Table",
  donut: "Donut chart",
  pie: "Pie chart",
  process: "Process",
  staircase: "Staircase",
  tiers: "Tiers",
  wheel: "Cycle",
  tile_grid: "Tile grid",
  fact_chips: "Fact chips",
  band: "Goal, approach, result",
  story_panel: "Case story",
  info_box: "Info box",
};

const KIND_LABEL: Record<string, string> = {
  cover: "Cover",
  agenda: "Agenda",
  divider: "Chapter divider",
  closing: "Closing",
};

/** In-chat slide viewer: a sharp main slide, thumbnails underneath, and a full-screen presenter. */
export function SlideViewer({
  slides,
  hd,
  meta,
  keyboard = true,
  present,
  setPresent,
}: {
  slides: string[];
  hd: string[];
  meta: ReportSlide[];
  keyboard?: boolean;
  present: boolean;
  setPresent: (v: boolean) => void;
}) {
  const [i, setI] = useState(0);
  const strip = useRef<HTMLDivElement>(null);
  const n = slides.length;
  const big = hd.length === n ? hd : slides;

  const key = slides.join("|");
  useEffect(() => setI(0), [key]);

  useEffect(() => {
    if (!keyboard || present) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowRight") setI((c) => Math.min(n - 1, c + 1));
      if (e.key === "ArrowLeft") setI((c) => Math.max(0, c - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [n, keyboard, present]);

  useEffect(() => {
    const box = strip.current;
    const el = box?.children[i] as HTMLElement | undefined;
    if (box && el) box.scrollTo({ left: el.offsetLeft - box.clientWidth / 2 + el.clientWidth / 2, behavior: "smooth" });
  }, [i]);

  if (!n) return null;
  const m = meta.find((x) => x.n === i + 1);

  return (
    <div>
      <div className="group relative overflow-hidden rounded-xl bg-white shadow-[0_1px_2px_rgba(27,26,23,0.06),0_8px_24px_-8px_rgba(27,26,23,0.18)] ring-1 ring-line">
        <img
          src={big[i]}
          alt={`Slide ${i + 1}`}
          className="aspect-video w-full cursor-pointer object-contain"
          onClick={() => setPresent(true)}
          draggable={false}
        />
        {i + 1 < n && <link rel="preload" as="image" href={big[i + 1]} />}
        <NavButton side="left" disabled={i === 0} onClick={() => setI(i - 1)} />
        <NavButton side="right" disabled={i === n - 1} onClick={() => setI(i + 1)} />
        <button
          type="button"
          onClick={() => setPresent(true)}
          className="absolute top-3 right-3 inline-flex items-center gap-1.5 rounded-full bg-ink/75 px-3 py-1.5 text-xs font-medium text-white opacity-0 backdrop-blur transition-opacity group-hover:opacity-100 hover:bg-ink/90"
        >
          <Play className="size-3 fill-current" /> Present
        </button>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="text-[13px] font-semibold text-ink tabular-nums">
          {i + 1} / {n}
        </span>
        {m && (
          <>
            <span className="min-w-0 truncate text-[13px] text-ink-2">
              {m.kind === "content" ? m.title : KIND_LABEL[m.kind]}
            </span>
            {m.kind === "content" && m.visual && (
              <Badge tone="brand" className="ml-auto">
                {VISUAL_LABEL[m.visual] ?? m.visual}
              </Badge>
            )}
          </>
        )}
      </div>

      <div ref={strip} className="scroll-thin relative mt-2.5 flex gap-2 overflow-x-auto pb-2">
        {slides.map((s, k) => (
          <button
            key={s}
            type="button"
            onClick={() => setI(k)}
            className={cx(
              "relative w-24 shrink-0 overflow-hidden rounded-md border-2 transition-all",
              k === i ? "border-brand" : "border-transparent opacity-75 hover:opacity-100",
            )}
            aria-label={`Slide ${k + 1}`}
          >
            <img src={s} alt="" loading="lazy" className="aspect-video w-full bg-white object-cover ring-1 ring-line" />
            <span className="absolute bottom-1 left-1 rounded bg-ink/70 px-1 text-[10px] font-medium text-white tabular-nums">
              {k + 1}
            </span>
          </button>
        ))}
      </div>

      {present && <Presenter slides={big} start={i} onClose={() => setPresent(false)} />}
    </div>
  );
}

function NavButton({ side, disabled, onClick }: { side: "left" | "right"; disabled: boolean; onClick: () => void }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={side === "left" ? "Previous slide" : "Next slide"}
      className={cx(
        "absolute top-1/2 -translate-y-1/2 rounded-full bg-white/95 p-2 text-ink shadow-pop ring-1 ring-line transition-opacity",
        side === "left" ? "left-3" : "right-3",
        disabled ? "pointer-events-none opacity-0" : "opacity-0 group-hover:opacity-100",
      )}
    >
      <Icon className="size-4" />
    </button>
  );
}
