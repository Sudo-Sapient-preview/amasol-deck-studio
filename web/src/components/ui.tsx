import { LoaderCircle } from "lucide-react";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

function buttonCls(variant: Variant, size: Size, className?: string) {
  const v: Record<Variant, string> = {
    primary:
      "bg-brand text-white hover:bg-brand-600 active:bg-brand-700 shadow-sm disabled:bg-line-strong disabled:text-white",
    secondary:
      "bg-white text-ink border border-line hover:border-line-strong hover:bg-canvas active:bg-line/50 shadow-card disabled:text-faint",
    ghost: "text-ink-2 hover:bg-line/60 hover:text-ink disabled:text-faint",
    danger: "bg-white text-signal border border-line hover:border-signal/40 hover:bg-signal-50",
  };
  const s = {
    sm: "h-8 px-2.5 text-[13px] gap-1.5 rounded-md",
    md: "h-9 px-3.5 text-sm gap-2 rounded-lg",
    lg: "h-11 px-5 text-[15px] gap-2 rounded-lg",
  }[size];
  return cx(
    "inline-flex select-none items-center justify-center font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed",
    v[variant],
    s,
    className,
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button className={buttonCls(variant, size, className)} {...rest} disabled={loading || rest.disabled}>
      {loading ? <LoaderCircle className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
  ...rest
}: AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant; size?: Size; icon?: ReactNode }) {
  return (
    <a className={buttonCls(variant, size, className)} {...rest}>
      {icon}
      {children}
    </a>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cx("rounded-xl border border-line bg-white shadow-card", className)}>{children}</section>;
}

export function Label({ children, hint, htmlFor }: { children: ReactNode; hint?: ReactNode; htmlFor?: string }) {
  return (
    <div className="mb-1.5 flex items-baseline justify-between gap-3">
      <label htmlFor={htmlFor} className="text-[13px] font-semibold text-ink">
        {children}
      </label>
      {hint && <span className="text-xs text-mute">{hint}</span>}
    </div>
  );
}

export const inputCls =
  "w-full rounded-lg border border-line bg-white px-3 text-sm text-ink placeholder:text-faint transition-colors hover:border-line-strong focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/12";

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  size = "md",
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex w-full rounded-lg border border-line bg-canvas p-0.5" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "flex-1 rounded-md font-medium transition-all",
            size === "sm" ? "h-6 px-2 text-xs" : "h-8 px-2.5 text-[13px]",
            value === o.value ? "bg-white text-ink shadow-card ring-1 ring-line" : "text-mute hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "neutral" | "brand" | "ok" | "warn" | "signal";
  children: ReactNode;
  className?: string;
}) {
  const t = {
    neutral: "bg-canvas text-ink-2 ring-line",
    brand: "bg-brand-50 text-brand-700 ring-brand-100",
    ok: "bg-ok-50 text-ok ring-ok/15",
    warn: "bg-warn-50 text-warn ring-warn/20",
    signal: "bg-signal-50 text-signal ring-signal/15",
  }[tone];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        t,
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-start gap-3 text-left"
    >
      <span
        className={cx(
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full transition-colors",
          checked ? "bg-brand" : "bg-line-strong",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-4.5" : "translate-x-0.5",
          )}
        />
      </span>
      <span>
        <span className="block text-[13px] font-semibold text-ink">{label}</span>
        {description && <span className="block text-xs text-mute">{description}</span>}
      </span>
    </button>
  );
}

export function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export function formatDuration(s: number) {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m ? `${m}:${String(r).padStart(2, "0")} min` : `${r} s`;
}

export function timeAgo(t: number) {
  const d = Date.now() / 1000 - t;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return new Date(t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
