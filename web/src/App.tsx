import { Presentation, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, reviseDeck, startDeck } from "./api";
import { Composer } from "./components/Composer";
import { DeckPanel, type PanelTab } from "./components/DeckPanel";
import { AssistantMessage, UserMessage } from "./components/Messages";
import { Sidebar, threadsFrom, type ThreadSummary } from "./components/Sidebar";
import { filesFromDrop, mergeFiles } from "./files";
import { useJobEvents } from "./hooks";
import type { AppConfig, Job, JobSummary, PickedFile } from "./types";

const readRoot = () => new URLSearchParams(location.search).get("deck");
const isLive = (s?: string) => s === "running" || s === "queued";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [root, setRoot] = useState<string | null>(readRoot());
  const [details, setDetails] = useState<Record<string, Job>>({});
  const [text, setText] = useState("");
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [panel, setPanel] = useState<{ id: string; tab: PanelTab } | null>(null);
  const [dragging, setDragging] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.config().then(setConfig, (e) => setNote(`Cannot reach the server: ${e.message}`));
  }, []);

  const refreshJobs = useCallback(() => api.jobs().then(setJobs, () => undefined), []);
  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  const fetchJob = useCallback(
    (id: string) =>
      api.job(id).then(
        (j) => setDetails((d) => ({ ...d, [id]: j })),
        () => undefined,
      ),
    [],
  );

  // URL keeps the open deck (?deck=<root id>)
  useEffect(() => {
    const url = new URL(location.href);
    if (root) url.searchParams.set("deck", root);
    else url.searchParams.delete("deck");
    history.replaceState(null, "", url);
    setPanel(null);
  }, [root]);

  const threads = useMemo(() => threadsFrom(jobs), [jobs]);
  const versions = useMemo(
    () => jobs.filter((j) => j.root_id === root).sort((a, b) => a.version - b.version),
    [jobs, root],
  );

  // load each version's details once, and again when its status changes in the list
  const seen = useRef<Record<string, string>>({});
  const versionsKey = versions.map((v) => `${v.id}:${v.status}`).join(",");
  useEffect(() => {
    for (const v of versions) {
      if (seen.current[v.id] !== v.status) {
        seen.current[v.id] = v.status;
        fetchJob(v.id);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionsKey, fetchJob]);

  // a deck that no longer exists (deleted, wrong link) closes the thread; checked against a fresh list
  useEffect(() => {
    if (!root || !jobs.length || jobs.some((j) => j.root_id === root)) return;
    let stale = false;
    api.jobs().then((fresh) => {
      if (stale) return;
      setJobs(fresh);
      if (!fresh.some((j) => j.root_id === root)) setRoot(null);
    }, () => undefined);
    return () => {
      stale = true;
    };
  }, [root, jobs]);

  const thread = versions.map((v) => details[v.id]).filter(Boolean) as Job[];
  const active = thread.find((j) => isLive(j.status)) ?? versions.find((v) => isLive(v.status));
  const activeId = active?.id ?? null;
  const events = useJobEvents(activeId, () => {
    if (activeId) fetchJob(activeId);
    refreshJobs();
  });

  // other decks still building: keep the sidebar fresh
  const anyBusy = threads.some((t) => t.busy);
  useEffect(() => {
    if (!anyBusy) return;
    const t = setInterval(refreshJobs, 8000);
    return () => clearInterval(t);
  }, [anyBusy, refreshJobs]);

  // stick to the bottom of the thread while new content arrives
  const nearBottom = useRef(true);
  useEffect(() => {
    const el = scroller.current;
    if (el && nearBottom.current) el.scrollTop = el.scrollHeight;
  }, [thread.length, events.length, thread.map((j) => j.status).join()]);
  useEffect(() => {
    nearBottom.current = true;
  }, [root]);

  const addFiles = useCallback(
    (incoming: PickedFile[]) => {
      if (!incoming.length) return;
      const r = mergeFiles(files, incoming, config?.limits ?? { file_mb: 60, files: 200 });
      setFiles(r.files);
      setNote(r.note);
    },
    [config, files],
  );

  // drop files or folders anywhere on the page
  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth++;
      setDragging(true);
    };
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (!depth) setDragging(false);
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      if (e.dataTransfer) filesFromDrop(e.dataTransfer).then(addFiles, () => setNote("Could not read the dropped files"));
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [addFiles]);

  const lastDone = [...thread].reverse().find((j) => j.status === "done");

  const send = async () => {
    const message = text.trim();
    if ((!message && !files.length) || sending || active) return;
    setSending(true);
    setNote(null);
    setProgress(files.length ? 0 : null);
    try {
      const res =
        root && lastDone
          ? await reviseDeck(lastDone.id, message, files, setProgress)
          : await startDeck(message, files, setProgress);
      setText("");
      setFiles([]);
      nearBottom.current = true;
      await refreshJobs(); // the list must know the new thread before it opens
      setRoot(res.root_id);
      fetchJob(res.id);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setSending(false);
      setProgress(null);
    }
  };

  const deleteThread = async (t: ThreadSummary) => {
    const all = jobs.filter((j) => j.root_id === t.root).sort((a, b) => b.version - a.version);
    for (const j of all) await api.remove(j.id).catch(() => undefined);
    if (root === t.root) setRoot(null);
    refreshJobs();
  };

  const newDeck = () => {
    setRoot(null);
    setText("");
    setFiles([]);
    setNote(null);
  };

  const composer = (
    <Composer
      text={text}
      setText={setText}
      files={files}
      setFiles={setFiles}
      onAddFiles={addFiles}
      onSend={send}
      onStop={active ? () => api.cancel(active.id).then(() => fetchJob(active.id)) : undefined}
      running={!!active}
      sending={sending}
      progress={progress}
      note={note}
      placeholder={
        !root
          ? "Describe the deck you need, paste notes or an outline, or drop files…"
          : active
            ? "Building the deck. You can ask for changes when it is ready."
            : lastDone
            ? "Ask for changes, or add files…"
            : "Describe the deck you need…"
      }
    />
  );

  const panelJob = panel ? details[panel.id] : null;

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-white/80 px-4 backdrop-blur">
        <button type="button" onClick={newDeck} className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-lg bg-brand">
            <Presentation className="size-4 text-white" />
          </span>
          <span className="font-display text-[17px] font-semibold tracking-tight text-ink">
            amasol <span className="font-normal text-mute">Deck Studio</span>
          </span>
        </button>
        <span className="hidden text-[11px] tracking-[0.08em] text-mute uppercase sm:block">
          Built on the amasol style guide
        </span>
        <button
          type="button"
          onClick={newDeck}
          className="text-[11px] font-medium tracking-[0.08em] text-brand uppercase sm:hidden"
        >
          New
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <Sidebar threads={threads} current={root} onOpen={setRoot} onNew={newDeck} onDelete={deleteThread} />

        <main className="flex min-w-0 flex-1 flex-col">
          {root ? (
            <>
              <div
                ref={scroller}
                onScroll={(e) => {
                  const el = e.currentTarget;
                  nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
                }}
                className="scroll-thin min-h-0 flex-1 overflow-y-auto"
              >
                <div className="mx-auto flex w-full max-w-[760px] flex-col gap-7 px-4 pt-8 pb-6">
                  {thread.length === 0 && <div className="h-40 animate-pulse rounded-xl bg-white/60" />}
                  {thread.map((j, k) => (
                    <div key={j.id} className="flex flex-col gap-5">
                      <UserMessage job={j} />
                      <AssistantMessage
                        job={j}
                        events={j.id === activeId ? events : []}
                        latest={k === thread.length - 1}
                        onOpenPanel={(tab) => setPanel({ id: j.id, tab })}
                        onRetry={() =>
                          api.retry(j.id).then(async (r) => {
                            await refreshJobs();
                            const fresh = await api.job(r.id);
                            setDetails((d) => ({ ...d, [r.id]: fresh }));
                            setRoot(fresh.root_id);
                          })
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div className="mx-auto w-full max-w-[760px] shrink-0 px-4 pb-4">{composer}</div>
            </>
          ) : (
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto w-full max-w-[720px] px-4 pt-[11vh] pb-10">
                <h1 className="text-center font-display text-[clamp(2.1rem,4.6vw,3.3rem)] leading-[1.12] font-semibold tracking-[-0.025em] text-ink">
                  <span className="block">Give it a brief,</span>
                  <span className="block">get back a deck</span>
                </h1>
                <p className="mx-auto mt-3 mb-12 max-w-md text-center text-sm text-mute">
                  Write what you need, paste notes or an outline, or drop in files and folders. Every deck follows
                  the amasol style guide and passes its checks.
                </p>
                {composer}
              </div>
            </div>
          )}
        </main>

        {panel && panelJob && (
          <DeckPanel
            job={panelJob}
            tab={panel.tab}
            setTab={(tab) => setPanel({ ...panel, tab })}
            onClose={() => setPanel(null)}
          />
        )}
      </div>

      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-canvas/75 p-6">
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-brand bg-white/95 px-12 py-10 shadow-pop">
            <span className="flex size-11 items-center justify-center rounded-full bg-brand-50">
              <Upload className="size-5 text-brand" />
            </span>
            <p className="font-display text-lg font-semibold text-ink">Drop to attach</p>
            <p className="text-xs text-mute">Files, folders and ZIPs</p>
          </div>
        </div>
      )}
    </div>
  );
}
