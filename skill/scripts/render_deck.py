"""Render a deck to <outdir>/<name>.pdf, slide-NN.jpg and contact.jpg with Outfit standing in for Mark Pro.

Usage: python3 scripts/render_deck.py out.pptx [outdir]      (outdir defaults to ./render)

Sets FONTCONFIG_FILE to this skill's reference/fonts-preview.conf as an ABSOLUTE path itself (a relative path is
silently ignored by fontconfig). Engine chain: the `office` CLI if on PATH, else LibreOffice (`soffice`/
`libreoffice --headless --convert-to pdf`) + poppler `pdftoppm`; the contact sheet needs Pillow (skipped if
missing). Exits 1 with a clear message if no engine is available."""
import glob, os, shutil, subprocess, sys, tempfile

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTCONF = os.path.join(SKILL, "reference", "fonts-preview.conf")
DPI = 110          # same default as `office render`: legible text, ~1100 px wide slides
SHEET_COLS = 4     # contact-sheet columns (matches `office render`)
TIMEOUT_S = 300    # LibreOffice cold start + a 60-slide deck stays well under this


def die(msg):
    sys.exit(f"render_deck: {msg}")


def font_env():
    env = dict(os.environ, FONTCONFIG_FILE=FONTCONF)
    if shutil.which("fc-match"):
        got = subprocess.run(["fc-match", "Mark Pro"], env=env, capture_output=True, text=True).stdout
        if "Outfit" not in got:
            print(f"render_deck: WARNING Mark Pro maps to '{got.strip()}', not Outfit - install the Outfit font "
                  "(Google Fonts, OFL) or previews will not match the guide", file=sys.stderr)
    return env


def contact_sheet(imgs, out):
    try:
        from PIL import Image
    except ImportError:
        print("render_deck: Pillow missing, contact sheet skipped (pip install pillow)", file=sys.stderr)
        return
    ims = [Image.open(p) for p in imgs]
    w, h = ims[0].size
    rows = (len(ims) + SHEET_COLS - 1) // SHEET_COLS
    sheet = Image.new("RGB", (w * SHEET_COLS, h * rows), "white")
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % SHEET_COLS) * w, (i // SHEET_COLS) * h))
    sheet.thumbnail((2400, 2400 * rows))
    sheet.save(out, quality=85)


def via_libreoffice(src, outdir, env):
    lo = shutil.which("soffice") or shutil.which("libreoffice")
    if not lo:
        die("neither the `office` CLI nor LibreOffice (soffice) is installed - install LibreOffice to render")
    if not shutil.which("pdftoppm"):
        die("pdftoppm (poppler-utils) is missing - install it to make slide images")
    with tempfile.TemporaryDirectory() as prof:   # private profile: avoids clashes with a running LibreOffice
        r = subprocess.run([lo, f"-env:UserInstallation=file://{prof}", "--headless", "--convert-to", "pdf",
                            "--outdir", outdir, src], env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
    pdf = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if not os.path.exists(pdf):
        die(f"LibreOffice produced no PDF (exit {r.returncode}): {r.stderr.strip()[:300]}")
    subprocess.run(["pdftoppm", "-jpeg", "-r", str(DPI), pdf, os.path.join(outdir, "slide")], check=True)
    imgs = sorted(glob.glob(os.path.join(outdir, "slide-*.jpg")))
    for p in imgs:      # pdftoppm pads to the page count's width; normalise to slide-NN.jpg
        n = int(os.path.basename(p)[6:-4])
        os.replace(p, os.path.join(outdir, f"slide-{n:02d}.jpg"))
    imgs = sorted(glob.glob(os.path.join(outdir, "slide-*.jpg")))
    if imgs:
        contact_sheet(imgs, os.path.join(outdir, "contact.jpg"))
    return pdf


def main():
    if len(sys.argv) not in (2, 3):
        die(__doc__)
    src = os.path.abspath(sys.argv[1])
    outdir = os.path.abspath(sys.argv[2] if len(sys.argv) == 3 else "render")
    if not os.path.isfile(src):
        die(f"no such file: {src}")
    os.makedirs(outdir, exist_ok=True)
    env = font_env()
    office = shutil.which("office")
    if office:
        r = subprocess.run([office, "render", src, outdir], env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
        if r.returncode == 0:
            print(f"rendered with office CLI -> {outdir}")
            return
        print(f"render_deck: office render failed ({r.stderr.strip()[:200]}), falling back to LibreOffice", file=sys.stderr)
    via_libreoffice(src, outdir, env)
    print(f"rendered with LibreOffice + pdftoppm -> {outdir}")


if __name__ == "__main__":
    main()
