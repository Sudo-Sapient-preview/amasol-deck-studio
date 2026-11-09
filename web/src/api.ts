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

/** On the Vercel-hosted UI, uploads go straight to the backend: Vercel's /api proxy drops bodies over a few MB.
 * Everywhere else (the backend serving the UI itself) uploads stay same-origin. */
const UPLOAD_BASE =
  location.hostname.endsWith(".vercel.app") && import.meta.env.VITE_BACKEND_URL
    ? String(import.meta.env.VITE_BACKEND_URL).replace(/\/$/, "")
    : "";

/** POST a multipart form with upload progress (fetch has no upload progress). */
function postForm(url: string, fd: FormData, onProgress: (fraction: number) => void): Promise<Created> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", UPLOAD_BASE + url);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: Partial<Created> & { error?: string } = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300 && body.id && body.root_id) resolve(body as Created);
      else reject(new Error(body.error || `Request failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error while sending"));
    xhr.send(fd);
  });
}

function addFiles(fd: FormData, files: PickedFile[]) {
  for (const f of files) {
    fd.append("files", f.file, f.file.name);
    fd.append("paths", f.path);
    fd.append("roles", f.role);
  }
}

/** First message of a new deck thread. */
export function startDeck(message: string, files: PickedFile[], onProgress: (f: number) => void) {
  const fd = new FormData();
  fd.append("brief", message);
  addFiles(fd, files);
  return postForm("/api/jobs", fd, onProgress);
}

/** Follow-up message in a thread: builds the next version from a finished one. */
export function reviseDeck(parentId: string, message: string, files: PickedFile[], onProgress: (f: number) => void) {
  const fd = new FormData();
  fd.append("feedback", message);
  addFiles(fd, files);
  return postForm(`/api/jobs/${parentId}/refine`, fd, onProgress);
}
