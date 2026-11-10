import { upload } from "@vercel/blob/client";
import type { AppConfig, Job, JobSummary, PickedFile } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.error) msg = body.error;
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => fetch("/api/config").then((r) => json<AppConfig>(r)),
  jobs: () => fetch("/api/jobs").then((r) => json<JobSummary[]>(r)),
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => json<Job>(r)),
  draft: (id: string) =>
    fetch(`/api/jobs/${id}/draft`).then((r) => (r.ok ? r.text() : Promise.reject(new Error("No draft")))),
  cancel: (id: string) => fetch(`/api/jobs/${id}/cancel`, { method: "POST" }).then((r) => json<{ ok: boolean }>(r)),
  retry: (id: string) => fetch(`/api/jobs/${id}/retry`, { method: "POST" }).then((r) => json<{ id: string }>(r)),
  remove: (id: string) => fetch(`/api/jobs/${id}`, { method: "DELETE" }).then((r) => json<{ ok: boolean }>(r)),
  fileUrl: (id: string, path: string, download = false) =>
    `/api/jobs/${id}/file/${path.split("/").map(encodeURIComponent).join("/")}${download ? "?download=1" : ""}`,
};

export interface Created {
  id: string;
  root_id: string;
}

interface UploadedFile {
  blob: string;
  name: string;
  path: string;
  role: string;
  size: number;
}

/** Upload each picked file straight to Vercel Blob (private store), reporting combined progress across all of them. */
async function uploadAll(files: PickedFile[], onProgress: (f: number) => void): Promise<UploadedFile[]> {
  if (!files.length) {
    onProgress(1);
    return [];
  }
  const session = crypto.randomUUID();
  const total = files.reduce((sum, f) => sum + f.file.size, 0);
  const loaded = new Array(files.length).fill(0);
  const report = () => onProgress(total ? loaded.reduce((a, b) => a + b, 0) / total : 1);

  const out: UploadedFile[] = new Array(files.length);
  let next = 0;
  // A dropped folder can hold up to 200 files: send 4 at a time, not all at once (Blob API rate limits).
  const lane = async () => {
    while (next < files.length) {
      const i = next++;
      const f = files[i];
      const blob = await upload(`uploads/${session}/${i}-${f.file.name}`, f.file, {
        access: "private",
        handleUploadUrl: "/api/upload",
        onUploadProgress: ({ loaded: l }) => {
          loaded[i] = l;
          report();
        },
      });
      out[i] = { blob: blob.pathname, name: f.file.name, path: f.path, role: f.role, size: f.file.size };
    }
  };
  await Promise.all(Array.from({ length: Math.min(4, files.length) }, lane));
  return out;
}

function postJson(url: string, body: unknown): Promise<Created> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => json<Created>(r));
}

/** First message of a new deck thread. */
export async function startDeck(message: string, files: PickedFile[], onProgress: (f: number) => void) {
  const uploaded = await uploadAll(files, onProgress);
  return postJson("/api/jobs", { brief: message, files: uploaded });
}

/** Follow-up message in a thread: builds the next version from a finished one. */
export async function reviseDeck(
  parentId: string,
  message: string,
  files: PickedFile[],
  onProgress: (f: number) => void,
) {
  const uploaded = await uploadAll(files, onProgress);
  return postJson(`/api/jobs/${parentId}/refine`, { feedback: message, files: uploaded });
}
