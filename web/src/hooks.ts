import { useEffect, useRef, useState } from "react";
import type { JobEvent } from "./types";

/** Follow a job's event stream (replays past events, then live ones; ends when the job is finished).
 * onChange runs on stage and status events so callers can refetch the job. */
export function useJobEvents(id: string | null, onChange?: (ev: JobEvent) => void) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const cb = useRef(onChange);
  cb.current = onChange;

  useEffect(() => {
    setEvents([]);
    if (!id) return;
    let closed = false;
    let es: EventSource | null = null;
    let last = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      es = new EventSource(`/api/jobs/${id}/events?after=${last}`);
      es.onmessage = (m) => {
        const ev = JSON.parse(m.data) as JobEvent;
        if (ev.seq <= last) return;
        last = ev.seq;
        setEvents((prev) => [...prev, ev]);
        if (ev.type !== "log") cb.current?.(ev);
      };
      es.addEventListener("end", () => {
        closed = true;
        es?.close();
        cb.current?.({ seq: last, t: Date.now() / 1000, type: "status" });
      });
      es.onerror = () => {
        es?.close();
        if (!closed) retry = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      es?.close();
    };
  }, [id]);

  return events;
}

export function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}
