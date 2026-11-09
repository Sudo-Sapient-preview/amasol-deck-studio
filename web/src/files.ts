import type { FileRole, PickedFile } from "./types";

export const IMAGE_RE = /\.(png|jpe?g|webp|gif|bmp)$/i;
const SKIP_RE = /(^|\/)(\.|__MACOSX\/|~\$)|(^|\/)(thumbs\.db|desktop\.ini)$/i;
const REF_DIR_RE = /(^|\/)(design|reference|references|refs?|brand|inspiration|moodboard)[^/]*\//i;

/** Files in a folder named like "design" or "reference" are design references; everything else is decided by the
 * server ("auto": documents are content, the model judges images). */
function roleFor(path: string): FileRole {
  return REF_DIR_RE.test(path) ? "reference" : "auto";
}

let counter = 0;
export function pick(file: File, path?: string): PickedFile {
  const p = path || (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
  return { key: `${Date.now()}-${counter++}`, file, path: p, role: roleFor(p) };
}

/** Walk a dropped folder (webkitGetAsEntry) and collect files with their relative paths. */
async function walk(entry: FileSystemEntry, prefix = ""): Promise<PickedFile[]> {
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
    return [pick(file, prefix + entry.name)];
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    const all: FileSystemEntry[] = [];
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
      if (!batch.length) break;
      all.push(...batch);
    }
    const nested = await Promise.all(all.map((e) => walk(e, `${prefix}${entry.name}/`)));
    return nested.flat();
  }
  return [];
}

/** Files from a drop event, folders included. Entries must be read synchronously inside the event handler. */
export async function filesFromDrop(dt: DataTransfer): Promise<PickedFile[]> {
  const entries = Array.from(dt.items || [])
    .filter((i) => i.kind === "file")
    .map((i) => i.webkitGetAsEntry?.())
    .filter(Boolean) as FileSystemEntry[];
  if (entries.length) return (await Promise.all(entries.map((e) => walk(e)))).flat();
  return Array.from(dt.files).map((f) => pick(f));
}

export interface Limits {
  file_mb: number;
  files: number;
}

/** Merge new files into the list: drops hidden/system files, oversized files and duplicates. */
export function mergeFiles(current: PickedFile[], incoming: PickedFile[], limits: Limits) {
  const notes: string[] = [];
  let list = incoming.filter((f) => !SKIP_RE.test(f.path));
  const big = list.filter((f) => f.file.size > limits.file_mb * 1024 ** 2);
  list = list.filter((f) => f.file.size <= limits.file_mb * 1024 ** 2);
  const seen = new Set(current.map((f) => `${f.path}:${f.file.size}`));
  list = list.filter((f) => !seen.has(`${f.path}:${f.file.size}`));
  const room = Math.max(0, limits.files - current.length);
  if (list.length > room) notes.push(`${list.length - room} file(s) over the limit of ${limits.files} left out`);
  if (big.length) notes.push(`${big.length} file(s) over ${limits.file_mb} MB left out`);
  return { files: [...current, ...list.slice(0, room)], note: notes.join(" · ") || null };
}
