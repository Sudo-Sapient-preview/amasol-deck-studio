import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cx } from "./ui";

/** Full-screen presentation: one slide at a time on black, keyboard and click navigation, controls that fade
 * out while idle. Uses the Fullscreen API when the browser allows it, otherwise fills the window. */
export function Presenter({ slides, start, onClose }: { slides: string[]; start: number; onClose: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [i, setI] = useState(start);
  const [idle, setIdle] = useState(false);
  const n = slides.length;
  const close = useRef(onClose);
  close.current = onClose;
  const go = useCallback((k: number) => setI(Math.min(n - 1, Math.max(0, k))), [n]);

  // fullscreen in, and leaving fullscreen (Esc) closes the presenter
  useEffect(() => {
    const el = root.current;
    let entered = false;
    const onChange = () => {
      if (document.fullscreenElement) entered = true;
      else if (entered) close.current();
    };
    document.addEventListener("fullscreenchange", onChange);
    el?.requestFullscreen?.().catch(() => undefined);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) {
        e.preventDefault();
        setI((c) => Math.min(n - 1, c + 1));
      } else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(e.key)) {
        e.preventDefault();
        setI((c) => Math.max(0, c - 1));
      } else if (e.key === "Home") setI(0);
      else if (e.key === "End") setI(n - 1);
      else if (e.key === "Escape") close.current(); // unmount exits fullscreen too
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [n]);

  // controls fade after 2.5 s without mouse movement
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wake = useCallback(() => {
    setIdle(false);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setIdle(true), 2500);
  }, []);
  useEffect(() => {
    wake();
    return () => clearTimeout(timer.current);
  }, [wake]);

  return (
    <div
      ref={root}
      onMouseMove={wake}
      className={cx("fixed inset-0 z-[60] flex items-center justify-center bg-black select-none", idle && "cursor-none")}
      role="dialog"
      aria-modal="true"
      aria-label="Presentation"
    >
      <img
        key={slides[i]}
        src={slides[i]}
        alt={`Slide ${i + 1} of ${n}`}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          go(e.clientX - r.left < r.width / 3 ? i - 1 : i + 1);
        }}
        className="max-h-full max-w-full object-contain"
        draggable={false}
      />
      {/* preload the neighbours so paging is instant */}
      {[i - 1, i + 1].filter((k) => k >= 0 && k < n).map((k) => (
        <link key={k} rel="preload" as="image" href={slides[k]} />
      ))}

      <div className="absolute inset-x-0 bottom-0 h-0.5 bg-white/10">
        <div className="h-full bg-white/50 transition-[width] duration-300" style={{ width: `${((i + 1) / n) * 100}%` }} />
      </div>

      <div
        className={cx(
          "absolute bottom-6 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full bg-white/10 p-1 text-white/90 backdrop-blur transition-opacity duration-300",
          idle ? "pointer-events-none opacity-0" : "opacity-100",
        )}
      >
        <button
          type="button"
          onClick={() => go(i - 1)}
          disabled={i === 0}
          aria-label="Previous slide"
          className="rounded-full p-2 hover:bg-white/15 disabled:opacity-30"
        >
          <ChevronLeft className="size-5" />
        </button>
        <span className="min-w-16 text-center text-sm tabular-nums">
          {i + 1} / {n}
        </span>
        <button
          type="button"
          onClick={() => go(i + 1)}
          disabled={i === n - 1}
          aria-label="Next slide"
          className="rounded-full p-2 hover:bg-white/15 disabled:opacity-30"
        >
          <ChevronRight className="size-5" />
        </button>
      </div>

      <button
        type="button"
        onClick={() => close.current()}
        aria-label="Exit presentation"
        className={cx(
          "absolute top-5 right-5 rounded-full bg-white/10 p-2 text-white/90 backdrop-blur transition-opacity duration-300 hover:bg-white/20",
          idle ? "pointer-events-none opacity-0" : "opacity-100",
        )}
      >
        <X className="size-5" />
      </button>
    </div>
  );
}
