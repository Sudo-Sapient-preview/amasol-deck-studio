"""Fetch the websites a user links in their message, as text sources for the deck.

Public addresses only: every host (and every redirect target) must resolve to public IP addresses, so a link
cannot make the server read its own or the tailnet's private services. Reads the linked page plus a few pages it
links to on the same site, and says plainly when a site is password-protected, empty or unreachable."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

URL_RE = re.compile(r"\bhttps?://[^\s<>\"'`)\]]+", re.I)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 DeckStudio"
MAX_BYTES = 3 * 2**20
MAX_URLS = 5
MAX_EXTRA_PAGES = 6
MAX_CHARS = 60_000
TIMEOUT = 15
PROTECTED_RE = re.compile(r"enter (store |using )?password|password protected|/password\b|log ?in to continue|"
                          r"sign in to continue|access denied|opening soon", re.I)


class Blocked(Exception):
    pass


def find_urls(text: str) -> list[str]:
    out = []
    for m in URL_RE.findall(text or ""):
        u = m.rstrip(".,;:!?")
        if u not in out:
            out.append(u)
    return out[:MAX_URLS]


def _check_host(url: str):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Blocked(f"not a web address: {url}")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror:
        raise Blocked(f"the address {parts.hostname} does not exist")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip in ipaddress.ip_network("100.64.0.0/10"):
            raise Blocked(f"{parts.hostname} is not a public address")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect())


def _get(url: str) -> tuple[str, str]:
    """(final url, html text)."""
    _check_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.5"})
    with _opener.open(req, timeout=TIMEOUT) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            raise Blocked(f"not a web page ({ctype or 'unknown type'})")
        data = r.read(MAX_BYTES)
        charset = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), data.decode(charset, "replace")


def page_text(raw: str) -> tuple[str, str, str]:
    """(title, meta description, readable text)."""
    title = html.unescape(re.sub(r"\s+", " ", (re.search(r"(?is)<title[^>]*>(.*?)</title>", raw) or [None, ""])[1])).strip()
    desc = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', raw)
    desc = html.unescape(desc.group(1)).strip() if desc else ""
    body = re.sub(r"(?is)<(script|style|noscript|svg|template|iframe)[^>]*>.*?</\1>", " ", raw)
    body = re.sub(r"(?is)<!--.*?-->", " ", body)
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|section|article|header|footer|nav)>", "\n", body)
    body = re.sub(r"(?i)<li[^>]*>", "- ", body)
    body = re.sub(r"(?i)<h([1-3])[^>]*>", lambda m: "\n" + "#" * (int(m.group(1)) + 1) + " ", body)
    body = html.unescape(re.sub(r"(?s)<[^>]+>", " ", body))
    lines = [" ".join(l.split()) for l in body.splitlines()]
    out, seen = [], set()
    for l in lines:
        if l and l not in seen:          # menus and footers repeat; keep the first copy
            seen.add(l)
            out.append(l)
    return title, desc, "\n".join(out)


def _same_site_links(raw: str, base: str) -> list[str]:
    host = urllib.parse.urlsplit(base).hostname
    links = []
    for href in re.findall(r'(?i)href=["\']([^"\'#]+)', raw):
        u = urllib.parse.urljoin(base, href.strip())
        p = urllib.parse.urlsplit(u)
        if p.hostname != host or p.scheme not in ("http", "https"):
            continue
        if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|css|js|ico|xml|json)$|/(cart|account|login|password|"
                     r"search|checkout|cdn)\b", p.path, re.I):
            continue
        u = urllib.parse.urlunsplit((p.scheme, p.netloc, p.path.rstrip("/") or "/", "", ""))
        if u not in links and u.rstrip("/") != base.rstrip("/"):
            links.append(u)
    return links


def fetch_site(url: str) -> tuple[str, list[str]]:
    """Text source for one linked site, and notes (problems) to show the user."""
    notes: list[str] = []
    try:
        final, raw = _get(url)
    except Blocked as e:
        return f"# Website: {url}\nNOT FETCHED: {e}.\n", [f"{url}: {e}"]
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", None) or getattr(e, "code", None) or e
        return f"# Website: {url}\nNOT FETCHED: the site could not be reached ({reason}).\n", \
            [f"{url}: could not be reached ({reason})"]
    title, desc, text = page_text(raw)
    parts = [f"# Website: {url}", f"Fetched {final}" + (f" (redirected from {url})" if final.rstrip("/") != url.rstrip("/") else "")]
    protected = bool(PROTECTED_RE.search(final)) or (len(text) < 1500 and bool(PROTECTED_RE.search(text)))
    if protected:
        parts.append("NOTE: the site is password-protected or not public yet. Only the page below is visible; "
                     "its real pages, products and content could not be read. Do not describe them.")
        notes.append(f"{url} is password-protected or not public yet, so only its holding page could be read")
    elif len(text) < 200:
        parts.append("NOTE: the page has almost no readable text (it may be built with scripts).")
        notes.append(f"{url} has almost no readable text")
    parts += [f"## Page: {final}", f"Title: {title}" if title else "", f"Description: {desc}" if desc else "", text]
    total = sum(len(p) for p in parts)
    if not protected:
        for link in _same_site_links(raw, final)[:MAX_EXTRA_PAGES]:
            if total > MAX_CHARS:
                break
            try:
                f2, raw2 = _get(link)
            except (Blocked, urllib.error.URLError, TimeoutError, OSError):
                continue
            t2, d2, x2 = page_text(raw2)
            chunk = "\n".join(p for p in (f"## Page: {f2}", f"Title: {t2}" if t2 else "", x2[:12_000]) if p)
            parts.append(chunk)
            total += len(chunk)
    return "\n".join(p for p in parts if p)[:MAX_CHARS] + "\n", notes
