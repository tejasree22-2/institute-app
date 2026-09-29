"""Imports worksheets from the worksheet repo (github.com/aikaryashala/first-steps, folder docs/,
published at aikaryashala.com/first-steps/). Run from the app (the "Sync from GitHub" button in
Library → Worksheets, see routers/worksheets.py) or from scripts/sync_worksheets.py.

The docs/ index.html links each subject (ganitham/index.html, coding/index.html, ...), and each
subject index lists its items as
    <li><a href="task0/x_worksheet.html">Task 0 - ...</a> <a href="task0/x_questions.html">[Questions]</a> <a href="task0/x_answers.html">[ans]</a></li>
    <li><a href="ref/01x.html">Ref 01 - ...</a></li>
Every list item becomes a worksheet under that subject, in the same order: the first link is its
topic page, the bracketed links are its question sheets and ("ans") answer sheets, up to two of
each (Questions / Extra Questions). The subject folder is mirrored into the stored_files table
(services/file_store.py, keys "content/<subject>/...") so the pages keep working with their .md and
assets/ files.

Re-running updates existing worksheets in place (batch assignments and student progress are kept).
"""
import os
import posixpath
import re
import shutil
import tempfile
import http.client
import socket
import ssl
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser

from .. import models
from ..config import settings
from . import file_store


class SyncError(Exception):
    pass


# ------------------------------------------------------------- sources ----
class UrlSource:
    """Reads the repo over HTTP(S) through one kept-alive connection.

    GitHub serves raw.githubusercontent.com from several addresses and one of them can be unreachable
    from a given network (seen here: every 4th request hung until its timeout, so a sync took minutes).
    So each address is tried with a short connect timeout and the one that answers is reused."""

    CONNECT_TIMEOUT = 5
    READ_TIMEOUT = 30

    def __init__(self, base_url):
        self.base = base_url if base_url.endswith("/") else base_url + "/"
        self._conn, self._origin = None, None

    def _connect(self, scheme, host, port):
        last_err = None
        for family, _type, _proto, _name, addr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
            try:
                sock = socket.create_connection(addr[:2], timeout=self.CONNECT_TIMEOUT)
            except OSError as err:
                last_err = err
                continue
            sock.settimeout(self.READ_TIMEOUT)
            if scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                conn = http.client.HTTPSConnection(host, port, timeout=self.READ_TIMEOUT)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=self.READ_TIMEOUT)
            conn.sock = sock
            return conn
        raise SyncError(f"Could not connect to {host}: {last_err}")

    def _get(self, url):
        parts = urllib.parse.urlsplit(url)
        origin = (parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        for attempt in range(2):  # the server may have closed the kept-alive connection meanwhile
            if self._conn is None or self._origin != origin:
                if self._conn:
                    self._conn.close()
                self._conn, self._origin = self._connect(*origin), origin
            try:
                self._conn.request("GET", path, headers={"User-Agent": "institute-app-worksheet-sync"})
                res = self._conn.getresponse()
                return res.status, res.getheader("Location"), res.read()
            except (http.client.HTTPException, OSError):
                self._conn.close()
                self._conn = None
                if attempt:
                    raise

    def read(self, rel):
        url = urllib.parse.urljoin(self.base, rel)
        for _ in range(5):
            status, location, data = self._get(url)
            if status in (301, 302, 303, 307, 308) and location:
                url = urllib.parse.urljoin(url, location)
                continue
            if status == 404:
                return None
            if status >= 400:
                raise SyncError(f"{url} answered HTTP {status}")
            return data
        raise SyncError(f"Too many redirects for {url}")

    def mirror(self, slug, dest, start_pages, log=print):
        _crawl(self, slug, dest, start_pages, log)


class RepoSource:
    def __init__(self, path):
        self.root = os.path.abspath(path)
        if not os.path.isfile(os.path.join(self.root, "index.html")) and os.path.isfile(os.path.join(self.root, "docs", "index.html")):
            self.root = os.path.join(self.root, "docs")  # pointed at the repo root
        if not os.path.isfile(os.path.join(self.root, "index.html")):
            raise SyncError(f"{self.root} has no index.html — point it at the folder holding the subjects index")

    def read(self, rel):
        path = os.path.join(self.root, rel)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def mirror(self, slug, dest, start_pages, log=print):
        shutil.copytree(os.path.join(self.root, slug), dest, ignore=shutil.ignore_patterns(".git*"))


# ------------------------------------------------------------- parsing ----
class _LinkListParser(HTMLParser):
    """Collects the <a> links of each <li> (comments are ignored by HTMLParser)."""

    def __init__(self):
        super().__init__()
        self.items, self._item, self._link = [], None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li":
            self._item = []
        elif tag == "a" and self._item is not None and attrs.get("href"):
            self._link = [attrs["href"], ""]

    def handle_data(self, data):
        if self._link is not None:
            self._link[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            self._item.append((self._link[0], " ".join(self._link[1].split())))
            self._link = None
        elif tag == "li" and self._item is not None:
            self.items.append(self._item)
            self._item = None


def link_items(html_bytes):
    p = _LinkListParser()
    p.feed(html_bytes.decode("utf-8", errors="replace"))
    return p.items


class _AssetRefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("href"):
            self.refs.append(attrs["href"])
        elif tag in ("script", "img", "source", "iframe") and attrs.get("src"):
            self.refs.append(attrs["src"])
        elif tag == "body" and attrs.get("data-md"):
            self.refs.append(attrs["data-md"])


def _refs_in(rel, data):
    text = data.decode("utf-8", errors="replace")
    if rel.endswith(".html"):
        p = _AssetRefParser()
        p.feed(text)
        # viewer.js renders <name>.md next to the page unless body[data-md] says otherwise
        return p.refs + [posixpath.basename(rel)[: -len(".html")] + ".md"]
    if rel.endswith(".md"):
        return re.findall(r"!\[[^\]]*\]\(([^)\s]+)", text) + re.findall(r'src="([^"]+)"', text)
    if rel.endswith(".css"):
        return re.findall(r"url\(['\"]?([^'\")]+)", text)
    return []


def _crawl(source, slug, dest, start_pages, log=print):
    queue, seen = [f"{slug}/{p}" for p in start_pages], set()
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.add(rel)
        data = source.read(rel)
        if data is None:
            if not rel.endswith(".md"):  # the .md twin is only a guess (some pages have none)
                log(f"    ! missing {rel}")
            continue
        out = os.path.join(dest, os.path.relpath(rel, slug))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        for ref in _refs_in(rel, data):
            ref = ref.split("#")[0].split("?")[0]
            if not ref or re.match(r"^([a-z][a-z0-9+.-]*:|/)", ref, re.I):
                continue  # absolute / CDN / data: URLs stay as they are
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), ref))
            if target.startswith(slug + "/"):
                queue.append(target)


# ---------------------------------------------------------------- sync ----
def parse_subjects(source):
    root = source.read("index.html")
    if root is None:
        raise SyncError("Could not read the subjects index.html from the worksheet repo")
    subjects = []
    for item in link_items(root):
        href, name = item[0]
        m = re.fullmatch(r"([^/]+)/index\.html", href)
        if m:
            subjects.append((m.group(1), name))
    return subjects


def parse_tasks(index_bytes, log=print):
    """[{"title", "files": {kind: (href, label)}}] for each list item of a subject index, in order."""
    tasks = []
    for links in link_items(index_bytes):
        if not links:
            continue
        (topic_href, title), rest = links[0], links[1:]
        files = {"topic": (topic_href, None)}
        sheets = [(href, text.strip("[] ")) for href, text in rest]
        is_answer = lambda label: re.search(r"\bans(wers?)?\b", label, re.I)
        questions = [s for s in sheets if not is_answer(s[1])]
        answers = [s for s in sheets if is_answer(s[1])]
        files.update(zip(("questions", "extra_questions"), questions))
        files.update(zip(("answers", "extra_answers"), answers))
        if len(questions) > 2 or len(answers) > 2:
            log(f"  ! {title}: only the first two question/answer links are imported")
        tasks.append({"title": title, "files": files})
    return tasks


def keep_missing_pages(old_dir, new_dir, pages, log=print):
    """A page the index still links but the repo no longer has (e.g. answer pages taken off the
    public site) keeps its previously synced copy, with the other files of its folder."""
    for page in pages:
        if os.path.isfile(os.path.join(new_dir, page)) or not os.path.isfile(os.path.join(old_dir, page)):
            continue
        log(f"    kept previous copy of {page}")
        folder = os.path.dirname(page)
        keep = [os.path.relpath(os.path.join(dirpath, f), old_dir)
                for dirpath, _dirs, filenames in os.walk(os.path.join(old_dir, folder)) for f in filenames]
        with open(os.path.join(old_dir, page), "rb") as f:
            refs = _refs_in(page, f.read())
        keep += [posixpath.normpath(posixpath.join(folder, r.split("#")[0].split("?")[0])) for r in refs
                 if not re.match(r"^([a-z][a-z0-9+.-]*:|/)", r, re.I)]  # shared files like ../assets/viewer.js
        for rel in keep:
            source_path, target = os.path.join(old_dir, rel), os.path.join(new_dir, rel)
            if not rel.startswith("..") and os.path.isfile(source_path) and not os.path.exists(target):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source_path, target)


def sync_subject(db, source, slug, name, instructor_id, log=print):
    """Mirrors one subject and upserts its worksheets. Returns one report row per item of the subject
    index — {"subject", "title", "worksheet_id", "status": new | existing | not_in_repo,
    "files": [{"kind", "label", "state": in_repo | kept | missing}]} — plus rows for worksheets that
    are no longer listed."""
    index = source.read(f"{slug}/index.html")
    if index is None:
        log(f"  ! {slug}/index.html not found, skipping")
        return []
    tasks = parse_tasks(index, log)
    log(f"{name}: {len(tasks)} item(s)")

    # build the new mirror in a temp dir (with the previous copy next to it, for pages taken off the
    # repo), then store it in place of the old one, so files removed upstream disappear too
    prefix = file_store.content_key(f"{slug}/")
    pages = [href for t in tasks for href, _ in t["files"].values()]
    with tempfile.TemporaryDirectory() as work:
        old_dir, new_dir = os.path.join(work, "old"), os.path.join(work, "new")
        file_store.export_prefix(db, prefix, old_dir)
        source.mirror(slug, new_dir, pages, log)
        os.makedirs(new_dir, exist_ok=True)
        in_repo = {page for page in pages if os.path.isfile(os.path.join(new_dir, page))}
        keep_missing_pages(old_dir, new_dir, pages, log)
        stored = file_store.replace_prefix(db, prefix, new_dir)

    now = datetime.now(timezone.utc)
    synced_keys, report = set(), []
    for position, t in enumerate(tasks):
        key = f"{slug}/{t['files']['topic'][0]}"
        synced_keys.add(key)
        w = db.query(models.WorksheetTask).filter(models.WorksheetTask.source_key == key).first()
        status = "existing" if w else "new"
        if not w:
            w = models.WorksheetTask(source_key=key, title=t["title"], description="", created_by=instructor_id)
            db.add(w)
            db.flush()
        row = {"subject": name, "title": t["title"], "worksheet_id": w.id, "status": status, "files": []}
        report.append(row)
        w.title, w.subject, w.subject_slug, w.position = t["title"], name, slug, position

        files_by_kind = {f.kind: f for f in w.files}
        for kind, record in files_by_kind.items():
            if kind not in t["files"]:
                db.delete(record)  # the link was removed from the index
        present = 0
        for kind, (href, label) in t["files"].items():
            rel_path = f"{slug}/{href}"
            is_stored = posixpath.normpath(href) in stored
            record = files_by_kind.get(kind)
            state = "in_repo" if href in in_repo else "kept" if is_stored else "missing"
            row["files"].append({"kind": kind, "label": label, "state": state})
            if not is_stored:
                log(f"    ! {rel_path} missing")
                if record:
                    db.delete(record)
                continue
            present += 1
            if not record:
                record = models.WorksheetFile(worksheet_id=w.id, kind=kind)
                db.add(record)
            record.original_filename = posixpath.basename(rel_path)
            record.stored_path = file_store.content_key(rel_path)
            record.rel_path = rel_path
            record.label = label
            record.content_type = "text/html"
            record.uploaded_at = now

        # the repo is the reviewed source, so it is verified straight away; files missing upstream
        # just can't be assigned (the instructor sees them greyed out)
        w.verified_at = (w.verified_at or now) if present else None
        log(f"  {'✓' if present == len(t['files']) else '!'} {t['title']}")

    stale = (
        db.query(models.WorksheetTask)
        .filter(models.WorksheetTask.subject_slug == slug, models.WorksheetTask.source_key.notin_(synced_keys))
        .all()
    )
    for w in stale:
        log(f"  ? no longer in {slug}/index.html (left untouched, delete it in the app if unwanted): {w.title}")
        report.append({"subject": name, "title": w.title, "worksheet_id": w.id, "status": "not_in_repo", "files": []})
    return report


def run_sync(db, source=None, subjects=None, instructor_id=None, log=print):
    """Syncs every subject of the repo index (or only the `subjects` slugs) and commits.
    Returns {"subjects": [names], "added": [titles of new worksheets], "items": [report rows, see sync_subject]}."""
    source = source or UrlSource(settings.worksheet_repo_url)
    if instructor_id is None:
        instructor = db.query(models.User).filter(models.User.role == "instructor").order_by(models.User.id).first()
        if not instructor:
            raise SyncError("No instructor account found")
        instructor_id = instructor.id

    found = parse_subjects(source)
    if subjects:
        found = [(slug, name) for slug, name in found if slug in subjects]
    if not found:
        raise SyncError("No subjects found to sync")
    items = []
    for slug, name in found:
        items += sync_subject(db, source, slug, name, instructor_id, log)
    db.commit()
    added = [r["title"] for r in items if r["status"] == "new"]
    return {"subjects": [name for _, name in found], "added": added, "items": items}
