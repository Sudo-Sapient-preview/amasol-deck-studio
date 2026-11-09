"""Turn uploaded files, folders and pasted text into plain-text sources and images for the model.

Every upload lands in WORK/inputs/<relative path>. Text goes to WORK/sources/NN-<name>.txt. Images (photos of
whiteboards, design references, rendered pages of reference decks) go to WORK/images/ as JPEG, at most 1568 px.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from PIL import Image

from . import config

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".htm",
            ".rst", ".log", ".eml", ".vtt", ".srt", ".rtf", ".ini", ".toml"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DOC_EXT = {".pdf", ".docx", ".pptx", ".xlsx", ".xlsm", ".odt", ".odp", ".doc", ".ppt"}
SKIP_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
MAX_IMG_SIDE = 1568
MAX_PAGES_AS_IMAGES = 6


@dataclass
class Source:
    name: str          # original relative path
    path: str          # WORK-relative text file
    chars: int
    kind: str          # pdf, docx, pptx, xlsx, text, pasted, brief


@dataclass
class ImageRef:
    name: str
    path: str          # WORK-relative JPEG
    role: str          # reference | content | auto


@dataclass
class IngestResult:
    sources: list[Source] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)


def safe_rel(name: str) -> str:
    """A safe relative POSIX path from an uploaded file name (keeps folder structure, drops traversal)."""
    parts = [p for p in PurePosixPath(name.replace("\\", "/")).parts if p not in ("", ".", "..", "/")]
    parts = [re.sub(r"[^\w.\- ()&+,@]", "_", p).strip() or "_" for p in parts]
    return "/".join(parts[-6:]) or "file"


def slug(name: str) -> str:
    s = re.sub(r"[^\w.-]+", "-", name).strip("-")
    return s[-80:] or "file"


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer|header|aside|form)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", raw)
    raw = re.sub(r"(?i)<li[^>]*>", "- ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    import html
    return html.unescape(raw)


def read_text_file(p: Path) -> str:
    data = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            t = data.decode(enc)
            if enc == "utf-16" and not data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            break
        except UnicodeDecodeError:
            continue
    else:
        t = data.decode("utf-8", "replace")
    if p.suffix.lower() in (".html", ".htm"):
        t = _html_to_text(t)
    if p.suffix.lower() == ".rtf":
        t = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", t)
    return t


def pdf_text(p: Path) -> str:
    try:
        r = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=120)
        return r.stdout
    except (OSError, subprocess.TimeoutExpired):
        from pypdf import PdfReader
        return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)


def docx_text(p: Path) -> str:
    import docx
    d = docx.Document(str(p))
    out = []
    body = d.element.body
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, d)
            t = para.text.strip()
            if not t:
                continue
            style = (para.style.name or "").lower() if para.style is not None else ""
            m = re.match(r"heading (\d)", style)
            if m:
                out.append("#" * min(int(m.group(1)) + 1, 4) + " " + t)
            elif style == "title":
                out.append("# " + t)
            elif "list" in style:
                out.append("- " + t)
            else:
                out.append(t)
        elif tag == "tbl":
            tbl = Table(child, d)
            for row in tbl.rows:
                cells = []
                for c in row.cells:
                    txt = " ".join(c.text.split())
                    if not cells or cells[-1] != txt:
                        cells.append(txt)
                out.append("| " + " | ".join(cells) + " |")
            out.append("")
    return "\n".join(out)


def pptx_text(p: Path) -> str:
    from pptx import Presentation
    prs = Presentation(str(p))
    out = []
    for i, slide in enumerate(prs.slides, 1):
        title = slide.shapes.title.text_frame.text.strip() if slide.shapes.title is not None and slide.shapes.title.has_text_frame else ""
        out.append(f"## Slide {i}: {title}".rstrip(": "))
        for sh in slide.shapes:
            if slide.shapes.title is not None and sh.shape_id == slide.shapes.title.shape_id:
                continue
            out.extend(_shape_lines(sh))
        if slide.has_notes_slide:
            n = slide.notes_slide.notes_text_frame.text.strip() if slide.notes_slide.notes_text_frame else ""
            if n:
                out.append("Speaker notes: " + " ".join(n.split()))
        out.append("")
    return "\n".join(out)


def _shape_lines(sh) -> list[str]:
    lines = []
    if sh.shape_type == 6 and hasattr(sh, "shapes"):          # group
        for s in sh.shapes:
            lines.extend(_shape_lines(s))
    if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
        for para in sh.text_frame.paragraphs:
            t = "".join(r.text for r in para.runs).strip()
            if t:
                lines.append("  " * para.level + "- " + t)
    if getattr(sh, "has_table", False) and sh.has_table:
        for row in sh.table.rows:
            lines.append("| " + " | ".join(" ".join(c.text.split()) for c in row.cells) + " |")
    if getattr(sh, "has_chart", False) and sh.has_chart:
        try:
            ch = sh.chart
            cats = list(ch.plots[0].categories)
            lines.append("Chart categories: " + ", ".join(str(c) for c in cats))
            for s in ch.plots[0].series:
                lines.append(f"Chart series {s.name}: " + ", ".join(str(v) for v in s.values))
        except Exception:  # noqa: BLE001 - charts without readable data are skipped
            pass
    return lines


def xlsx_text(p: Path) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"## Sheet: {ws.title}")
        buf = io.StringIO()
        w = csv.writer(buf)
        n = 0
        for row in ws.iter_rows(values_only=True):
            if row is None or all(v is None or str(v).strip() == "" for v in row):
                continue
            vals = ["" if v is None else str(v) for v in row]
            while vals and vals[-1] == "":
                vals.pop()
            w.writerow(vals)
            n += 1
            if n >= 400:
                buf.write("... (more rows not shown)\n")
                break
        out.append(buf.getvalue())
    return "\n".join(out)


def save_image(src: Path | Image.Image, dest: Path) -> Path:
    img = src if isinstance(src, Image.Image) else Image.open(src)
    try:
        img.seek(0)
    except Exception:  # noqa: BLE001
        pass
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((MAX_IMG_SIDE, MAX_IMG_SIDE))
    dest = dest.with_suffix(".jpg")
    img.save(dest, "JPEG", quality=85)
    return dest


def pdf_pages_to_images(pdf: Path, dest_dir: Path, stem: str, pages: int = MAX_PAGES_AS_IMAGES) -> list[Path]:
    tmp = Path(tempfile.mkdtemp(prefix="pg-", dir=dest_dir))
    try:
        subprocess.run(["pdftoppm", "-jpeg", "-r", "80", "-f", "1", "-l", str(pages), str(pdf), str(tmp / "p")],
                       capture_output=True, timeout=180)
        out = []
        for k, f in enumerate(sorted(tmp.glob("p*.jpg")), 1):
            out.append(save_image(f, dest_dir / f"{stem}-page{k:02d}"))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def office_to_pdf(src: Path, out_dir: Path) -> Path | None:
    profile = Path(tempfile.mkdtemp(prefix="lo-"))
    try:
        subprocess.run(["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf",
                        "--outdir", str(out_dir), str(src)], capture_output=True, timeout=240)
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    pdf = out_dir / (src.stem + ".pdf")
    return pdf if pdf.exists() else None


def extract_zip(zp: Path, dest: Path, warnings: list[str]) -> list[Path]:
    out, total = [], 0
    try:
        with zipfile.ZipFile(zp) as z:
            members = [m for m in z.infolist() if not m.is_dir()]
            if len(members) > config.MAX_ZIP_MEMBERS:
                warnings.append(f"{zp.name}: {len(members)} files in the archive, only the first "
                                f"{config.MAX_ZIP_MEMBERS} were read")
                members = members[: config.MAX_ZIP_MEMBERS]
            for m in members:
                rel = safe_rel(m.filename)
                if rel.split("/")[0] == "__MACOSX" or PurePosixPath(rel).name.lower() in SKIP_NAMES:
                    continue
                total += m.file_size
                if total > config.MAX_ZIP_TOTAL:
                    warnings.append(f"{zp.name}: archive larger than {config.MAX_ZIP_TOTAL // 2**20} MB unpacked, "
                                    "the rest was skipped")
                    break
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(m) as fsrc, open(target, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                out.append(target)
    except zipfile.BadZipFile:
        warnings.append(f"{zp.name}: not a readable zip archive")
    return out


def ingest(work: Path, uploads: list[tuple[str, Path, str]], pasted: str = "",
           pasted_name: str = "Pasted content") -> IngestResult:
    """uploads: (original relative name, saved path, role 'content' | 'reference' | 'auto').

    'auto' (the chat default) reads documents as content and shows images to the model, which decides whether an
    image carries facts or is a design reference. Numbering continues after files already in work/sources and
    work/images, so a revision can add uploads to an existing job folder."""
    res = IngestResult()
    src_dir, img_dir = work / "sources", work / "images"
    src_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(src_dir.glob("*.txt")))
    img_base = len(list(img_dir.glob("*.jpg")))

    def img_stem(name: str) -> str:
        return f"{img_base + len(res.images) + 1:02d}-{slug(PurePosixPath(name).stem)}"

    def add_text(name: str, text: str, kind: str):
        nonlocal n
        text = _clean(text)
        if not text:
            res.warnings.append(f"{name}: no readable text")
            return
        n += 1
        fn = f"{n:02d}-{slug(PurePosixPath(name).stem)}.txt"
        (src_dir / fn).write_text(text + "\n", encoding="utf-8")
        res.sources.append(Source(name=name, path=f"sources/{fn}", chars=len(text), kind=kind))

    def add_image(name: str, path: Path | Image.Image, role: str):
        try:
            dest = save_image(path, img_dir / img_stem(name))
        except Exception as e:  # noqa: BLE001
            res.warnings.append(f"{name}: image could not be read ({e})")
            return
        res.images.append(ImageRef(name=name, path=f"images/{dest.name}", role=role))

    if pasted.strip():
        add_text(pasted_name, pasted, "pasted")

    queue = list(uploads)
    while queue:
        name, path, role = queue.pop(0)
        ext = path.suffix.lower()
        base = PurePosixPath(name).name.lower()
        if base in SKIP_NAMES or base.startswith("~$") or base.startswith("._"):
            continue
        res.files.append({"name": name, "role": role, "bytes": path.stat().st_size})
        try:
            if ext == ".zip":
                unz = work / "inputs" / (safe_rel(name) + ".unzipped")
                for f in extract_zip(path, unz, res.warnings):
                    queue.append((f"{name}/{f.relative_to(unz).as_posix()}", f, role))
                continue
            if ext in IMAGE_EXT:
                add_image(name, path, role)
            elif role == "reference" and ext in (".pdf", ".pptx", ".ppt", ".odp", ".docx", ".doc", ".odt"):
                pdf = path if ext == ".pdf" else office_to_pdf(path, work / "inputs")
                pages = pdf_pages_to_images(pdf, img_dir, img_stem(name)) if pdf else []
                for k, pg in enumerate(pages, 1):
                    res.images.append(ImageRef(name=f"{name} (page {k})", path=f"images/{pg.name}", role="reference"))
                if not pages:
                    res.warnings.append(f"{name}: could not render pages of this reference file")
            elif ext == ".pdf":
                text = pdf_text(path)
                if len(text.strip()) < 80:          # scanned PDF: show the pages instead
                    pages = pdf_pages_to_images(path, img_dir, img_stem(name))
                    for k, pg in enumerate(pages, 1):
                        res.images.append(ImageRef(name=f"{name} (page {k})", path=f"images/{pg.name}", role="content"))
                    res.warnings.append(f"{name}: no text layer, the first {len(pages)} pages are read as images")
                else:
                    add_text(name, text, "pdf")
            elif ext == ".docx":
                add_text(name, docx_text(path), "docx")
            elif ext == ".pptx":
                add_text(name, pptx_text(path), "pptx")
            elif ext in (".xlsx", ".xlsm"):
                add_text(name, xlsx_text(path), "xlsx")
            elif ext in (".doc", ".ppt", ".odt", ".odp"):
                pdf = office_to_pdf(path, work / "inputs")
                if pdf:
                    add_text(name, pdf_text(pdf), "office")
                else:
                    res.warnings.append(f"{name}: could not convert this file")
            elif ext in TEXT_EXT or ext == "":
                add_text(name, read_text_file(path), "text")
            else:
                try:
                    t = path.read_bytes()[:2_000_000].decode("utf-8")
                    add_text(name, t, "text")
                except UnicodeDecodeError:
                    res.warnings.append(f"{name}: unsupported file type '{ext}', skipped")
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the job
            res.warnings.append(f"{name}: could not be read ({type(e).__name__}: {e})")

    if len(res.images) > config.MAX_REFERENCE_IMAGES:
        res.warnings.append(f"{len(res.images)} images uploaded; the model sees the first {config.MAX_REFERENCE_IMAGES}")
    return res
