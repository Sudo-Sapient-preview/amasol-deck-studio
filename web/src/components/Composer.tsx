import {
  ArrowUp,
  File as FileIcon,
  FileArchive,
  FileSpreadsheet,
  FileText,
  Paperclip,
  Presentation,
  Square,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { IMAGE_RE, pick } from "../files";
import type { PickedFile } from "../types";
import { cx, formatBytes } from "./ui";

export function fileIcon(name: string) {
  const n = name.toLowerCase();
  if (/\.(pptx?|odp|key)$/.test(n)) return Presentation;
  if (/\.(xlsx?|xlsm|csv|tsv|ods)$/.test(n)) return FileSpreadsheet;
  if (/\.zip$/.test(n)) return FileArchive;
  if (/\.(pdf|docx?|odt|txt|md|markdown|rtf|html?)$/.test(n)) return FileText;
  return FileIcon;
}

function Chip({ f, onRemove }: { f: PickedFile; onRemove: () => void }) {
  const isImg = IMAGE_RE.test(f.path);
  const url = useMemo(() => (isImg ? URL.createObjectURL(f.file) : null), [f.file, isImg]);
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  const Icon = fileIcon(f.path);
  const slash = f.path.lastIndexOf("/");
  return (
    <div className="flex max-w-[260px] min-w-0 items-center gap-2 rounded-xl border border-line bg-canvas py-1.5 pr-1.5 pl-1.5">
      {url ? (
        <img src={url} alt="" className="size-9 shrink-0 rounded-lg object-cover" />
      ) : (
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white ring-1 ring-line">
          <Icon className="size-4 text-mute" />
        </span>
      )}
      <div className="min-w-0 flex-1 leading-tight">
        <p className="truncate text-[12.5px] font-medium text-ink" title={f.path}>
          {f.path.slice(slash + 1)}
        </p>
        <p className="truncate text-[11px] text-mute">
          {slash > 0 ? `${f.path.slice(0, slash)} · ` : ""}
          {formatBytes(f.file.size)}
        </p>
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${f.path}`}
        className="flex size-5 shrink-0 items-center justify-center rounded-full bg-ink/70 text-white hover:bg-ink"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}

export function Composer({
  text,
  setText,
  files,
  setFiles,
  onAddFiles,
  onSend,
  onStop,
  running,
  sending,
  progress,
  placeholder,
  note,
}: {
  text: string;
  setText: (t: string) => void;
  files: PickedFile[];
  setFiles: (f: PickedFile[]) => void;
  onAddFiles: (f: PickedFile[]) => void;
  onSend: () => void;
  onStop?: () => void;
  running: boolean;
  sending: boolean;
  progress: number | null;
  placeholder: string;
  note: string | null;
}) {
  const ta = useRef<HTMLTextAreaElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const canSend = !running && !sending && (text.trim().length > 0 || files.length > 0);

  // grow with the text, up to a limit
  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
  }, [text]);

  const total = files.reduce((s, f) => s + f.file.size, 0);

  return (
    <form
      className="rounded-2xl border border-line bg-white p-3.5 pb-3 shadow-[0_10px_30px_rgba(27,26,23,0.05)] transition-shadow focus-within:border-line-strong focus-within:shadow-[0_12px_34px_rgba(27,26,23,0.08)]"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSend();
      }}
    >
      {files.length > 0 && (
        <div className="mb-2.5">
          <div className="scroll-thin flex max-h-40 flex-wrap gap-2 overflow-y-auto">
            {files.map((f) => (
              <Chip key={f.key} f={f} onRemove={() => setFiles(files.filter((x) => x.key !== f.key))} />
            ))}
          </div>
          {files.length > 1 && (
            <p className="mt-1.5 text-[11px] text-mute">
              {files.length} files · {formatBytes(total)} ·{" "}
              <button type="button" className="underline underline-offset-2 hover:text-ink" onClick={() => setFiles([])}>
                remove all
              </button>
            </p>
          )}
        </div>
      )}
      <textarea
        ref={ta}
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (canSend) onSend();
          }
        }}
        onPaste={(e) => {
          const pasted = Array.from(e.clipboardData.files);
          if (pasted.length) {
            e.preventDefault();
            onAddFiles(pasted.map((f) => pick(f, f.name === "image.png" ? `pasted-${Date.now()}.png` : f.name)));
          }
        }}
        placeholder={placeholder}
        aria-label="Message"
        className="scroll-thin block min-h-[72px] w-full resize-none bg-transparent px-1 text-[15px] leading-relaxed text-ink placeholder:text-faint focus:outline-none focus-visible:outline-none"
      />
      <div className="mt-2 flex items-center gap-2 border-t border-line/70 pt-2.5">
        <button
          type="button"
          onClick={() => input.current?.click()}
          className="flex size-9 items-center justify-center rounded-full border border-line text-mute transition-colors hover:border-line-strong hover:text-ink"
          aria-label="Attach files"
          title="Attach files (or drop files and folders anywhere)"
        >
          <Paperclip className="size-4" />
        </button>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            onAddFiles(Array.from(e.target.files || []).map((f) => pick(f)));
            e.target.value = "";
          }}
        />
        <span className="min-w-0 flex-1 truncate text-xs text-mute">{note}</span>
        {running && onStop ? (
          <button
            type="button"
            onClick={onStop}
            className="inline-flex h-9 items-center gap-1.5 rounded-full border border-brand px-4 text-[13px] font-medium text-brand hover:bg-brand-50"
          >
            <Square className="size-3 fill-current" /> Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            className={cx(
              "inline-flex h-9 min-w-[84px] items-center justify-center gap-1.5 rounded-full px-4 text-[13px] font-medium transition-colors",
              canSend ? "bg-brand text-white hover:bg-brand-600" : "bg-line text-faint",
            )}
          >
            {sending ? (progress !== null && progress < 1 ? `${Math.round(progress * 100)} %` : "Sending") : "Send"}
            {!sending && <ArrowUp className="size-3.5" />}
          </button>
        )}
      </div>
    </form>
  );
}
