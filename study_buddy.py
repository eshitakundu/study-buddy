"""
Study Buddy: an MCP server that turns Claude into a focused exam coach for a single subject.

Drop notes into materials/content/ and past papers into materials/pyqs/.
Claude discovers topics from the material, teaches them in any style, quizzes on them,
and runs PYQ-pattern practice. SQLite tracks results per topic so weakest ones surface first.
"""

import difflib
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Annotated

from pydantic import Field

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.prompts import base


mcp = FastMCP("study-buddy")

ROOT = Path(__file__).parent
MATERIALS_DIR = ROOT / "materials"
CONTENT_DIR = MATERIALS_DIR / "content"
PYQS_DIR = MATERIALS_DIR / "pyqs"
ARCHIVE_DIR = MATERIALS_DIR / "archive"
DB_PATH = ROOT / "study.db"

for d in (CONTENT_DIR, PYQS_DIR, ARCHIVE_DIR):
    d.mkdir(parents=True, exist_ok=True)


# database

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL REFERENCES topics(id),
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


_init_db()


# file helpers

TEXT_EXTS = {".txt", ".md"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VALID_FOLDERS = {"content", "pyqs", "archive"}

_text_cache: dict[tuple[str, float], str] = {}


def _folder_path(folder: str) -> Path:
    if folder not in VALID_FOLDERS:
        raise ValueError(f"folder must be one of {sorted(VALID_FOLDERS)}.")
    return MATERIALS_DIR / folder


def _safe_path(folder: str, name: str) -> Path:
    base_dir = _folder_path(folder)
    path = (base_dir / name).resolve()
    if not path.is_relative_to(base_dir.resolve()):
        raise ValueError("Access outside the materials folder is not allowed.")
    return path


def _extract_text(path: Path) -> str | None:
    # cached by (path, mtime) so repeated reads of the same file do not re-parse
    if not path.exists() or not path.is_file():
        return None
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return None
    key = (str(path), path.stat().st_mtime)
    if key in _text_cache:
        return _text_cache[key]
    if ext in TEXT_EXTS:
        text = path.read_text(encoding="utf-8", errors="ignore")
    elif ext == ".pdf":
        from pypdf import PdfReader
        text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    elif ext == ".docx":
        from docx import Document
        text = "\n".join(p.text for p in Document(str(path)).paragraphs)
    else:
        return None
    _text_cache[key] = text
    return text


def _list_folder(folder: str) -> list[dict]:
    items = []
    for p in sorted(_folder_path(folder).iterdir()):
        if p.is_file():
            items.append({
                "name": p.name,
                "type": p.suffix.lower().lstrip("."),
                "size_kb": round(p.stat().st_size / 1024, 1),
            })
    return items


# topic helpers

def _normalize_topic(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _registered_topics() -> list[str]:
    with _db() as conn:
        return [r["name"] for r in conn.execute("SELECT name FROM topics").fetchall()]


def _match_topic(name: str) -> str | None:
    # exact match first, then fuzzy fallback so 'loops' matches 'loop', etc.
    target = _normalize_topic(name)
    registered = _registered_topics()
    if target in registered:
        return target
    close = difflib.get_close_matches(target, registered, n=1, cutoff=0.7)
    return close[0] if close else None


# materials tools

@mcp.tool(title="List content files")
def list_content():
    """List all files in materials/content/ (your notes, slides, textbook extracts)."""
    return _list_folder("content")


@mcp.tool(title="List PYQ files")
def list_pyqs():
    """List all files in materials/pyqs/ (your previous-year question papers)."""
    return _list_folder("pyqs")


@mcp.tool(title="Read a file")
def read_file(
    folder: Annotated[str, Field(description="Which folder: 'content', 'pyqs', or 'archive'.")],
    name: Annotated[str, Field(description="Filename inside that folder.")],
):
    """Read a single file by folder + filename. Supports .txt, .md, .pdf, .docx, and images."""
    path = _safe_path(folder, name)
    if not path.exists():
        return f"No file named '{name}' in materials/{folder}/."
    if path.suffix.lower() in IMAGE_EXTS:
        return Image(path=str(path))
    text = _extract_text(path)
    if text is None:
        return f"Unsupported file type: {path.suffix}"
    return text.strip() or "(No extractable text. This may be a scanned PDF.)"


@mcp.tool(title="Search content")
def search_content(
    query: Annotated[str, Field(description="Word or phrase to search for in content files.")],
    max_results: Annotated[int, Field(description="Maximum number of matching files to return.", ge=1, le=20)] = 5,
):
    """Search across all files in materials/content/."""
    q = query.lower().strip()
    if not q:
        return []
    hits = []
    for p in sorted(CONTENT_DIR.iterdir()):
        if not p.is_file():
            continue
        text = _extract_text(p)
        if not text:
            continue
        idx = text.lower().find(q)
        if idx == -1:
            continue
        start = max(0, idx - 60)
        end = min(len(text), idx + len(q) + 60)
        snippet = text[start:end].replace("\n", " ").strip()
        hits.append({"name": p.name, "snippet": f"...{snippet}..."})
        if len(hits) >= max_results:
            break
    return hits


# topic discovery + registration

_HEADING_RE = re.compile(r"^(?:#{1,6}\s+(.+)|([A-Z][A-Za-z0-9 ,/&-]{2,60})$)", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*([^*]{2,40})\*\*")
_STEM_RE = re.compile(
    r"(?:^|\s)(?:Define|Explain|Describe|State|Derive|Discuss|What is|What are)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9 ,/&-]{2,60})",
    re.IGNORECASE,
)


def _candidate_topics_from_text(text: str) -> list[str]:
    cands: list[str] = []
    for m in _HEADING_RE.finditer(text):
        cands.append((m.group(1) or m.group(2) or "").strip())
    cands.extend(m.group(1).strip() for m in _BOLD_RE.finditer(text))
    cands.extend(m.group(1).strip().rstrip(".?,") for m in _STEM_RE.finditer(text))
    out = []
    for c in cands:
        c = re.sub(r"\s+", " ", c).strip(" :.-")
        c = re.sub(r"^(?:a|an|the)\s+", "", c, flags=re.IGNORECASE)
        if 3 <= len(c) <= 60 and not c.isupper():
            out.append(c)
    return out


@mcp.tool(title="Discover topics")
def discover_topics(
    min_count: Annotated[int, Field(description="Minimum times a candidate must appear to be returned.", ge=1)] = 2,
):
    """Scan all materials and return ranked candidate topics."""
    from collections import Counter
    counter: Counter[str] = Counter()
    for folder in (CONTENT_DIR, PYQS_DIR):
        for p in sorted(folder.iterdir()):
            if not p.is_file():
                continue
            text = _extract_text(p)
            if not text:
                continue
            for cand in _candidate_topics_from_text(text):
                counter[_normalize_topic(cand)] += 1
    registered = set(_registered_topics())
    return [
        {"topic": name, "count": cnt, "already_registered": name in registered}
        for name, cnt in counter.most_common(30)
        if cnt >= min_count
    ]


@mcp.tool(title="Register a topic")
def register_topic(
    name: Annotated[str, Field(description="Topic name to add to the tracker.")],
):
    """Add a topic to the tracker so quiz results can be logged against it."""
    norm = _normalize_topic(name)
    if not norm:
        return "Topic name cannot be empty."
    with _db() as conn:
        try:
            conn.execute("INSERT INTO topics (name) VALUES (?)", (norm,))
            return f"Registered topic: {norm}"
        except sqlite3.IntegrityError:
            return f"Topic '{norm}' is already registered."


@mcp.tool(title="List topics")
def list_topics(
    include_archived: Annotated[bool, Field(description="Include archived (mastered) topics in the result.")] = False,
):
    """List every registered topic with attempts, mastery %, and archived status."""
    with _db() as conn:
        where = "" if include_archived else "WHERE t.archived = 0"
        rows = conn.execute(f"""
            SELECT t.name,
                   t.archived,
                   COUNT(r.id) AS attempts,
                   COALESCE(SUM(r.score), 0) AS total_score,
                   COALESCE(SUM(r.total), 0) AS total_questions,
                   MAX(r.created_at) AS last_attempt
            FROM topics t
            LEFT JOIN results r ON r.topic_id = t.id
            {where}
            GROUP BY t.id
            ORDER BY t.archived ASC, last_attempt DESC NULLS LAST, t.name ASC
        """).fetchall()
    out = []
    for r in rows:
        tq = r["total_questions"]
        out.append({
            "topic": r["name"],
            "attempts": r["attempts"],
            "mastery_pct": round(100 * r["total_score"] / tq) if tq else 0,
            "last_attempt": r["last_attempt"],
            "archived": bool(r["archived"]),
        })
    return out


@mcp.tool(title="Archive a topic")
def archive_topic(
    name: Annotated[str, Field(description="Topic name to archive (mark mastered).")],
):
    """Archive a topic so it stops showing up in the active tracker. Files are not moved."""
    matched = _match_topic(name)
    if not matched:
        return f"No registered topic matches '{name}'."
    with _db() as conn:
        conn.execute("UPDATE topics SET archived = 1 WHERE name = ?", (matched,))
    return f"Archived topic: {matched}"


# progress

@mcp.tool(title="Log a quiz result")
def log_result(
    topic: Annotated[str, Field(description="Topic the quiz covered. Must be a registered topic.")],
    score: Annotated[int, Field(description="Number of questions you got right.", ge=0)],
    total: Annotated[int, Field(description="Total number of questions in the quiz.", ge=1)],
):
    """Record a quiz or test result against a registered topic."""
    if score > total:
        return f"Score must be between 0 and {total}."
    matched = _match_topic(topic)
    if not matched:
        return (
            f"No registered topic matches '{topic}'. "
            f"Call register_topic first, or use discover_topics to find one."
        )
    with _db() as conn:
        row = conn.execute("SELECT id FROM topics WHERE name = ?", (matched,)).fetchone()
        conn.execute(
            "INSERT INTO results (topic_id, score, total) VALUES (?, ?, ?)",
            (row["id"], score, total),
        )
    pct = round(100 * score / total)
    return f"Logged: {matched} -> {score}/{total} ({pct}%)."


@mcp.tool(title="Weakest topics")
def weakest_topics(
    n: Annotated[int, Field(description="How many of the weakest topics to return.", ge=1, le=20)] = 3,
):
    """Return the n topics with the lowest mastery. Ignores archived topics."""
    rows = list_topics(include_archived=False)
    rows.sort(key=lambda r: (r["mastery_pct"], -r["attempts"]))
    return rows[:n]


# PYQ analysis

_QUESTION_SPLIT_RE = re.compile(
    r"(?m)^(?:Q\.?\s*\d+|Question\s+\d+|\d{1,2}[.)])\s*[:.\-]?\s*"
)
_MARKS_RE = re.compile(r"\[?\(?\s*(\d{1,3})\s*marks?\s*\]?\)?", re.IGNORECASE)
_MCQ_RE = re.compile(r"(?m)^\s*\(?[a-d]\)?[.\)]\s+", re.IGNORECASE)


def _parse_pyq_questions(text: str) -> list[str]:
    parts = _QUESTION_SPLIT_RE.split(text)
    if len(parts) <= 1:
        parts = re.split(r"\n\s*\n", text)
    qs = []
    for part in parts:
        q = re.sub(r"\s+", " ", part).strip()
        if 10 <= len(q) <= 1000:
            qs.append(q)
    return qs


def _classify_question(q: str) -> str:
    if _MCQ_RE.search(q):
        return "mcq"
    if re.search(r"\b(calculate|compute|find the value|solve)\b", q, re.IGNORECASE):
        return "numerical"
    if len(q) < 120:
        return "short"
    return "long"


def _stem_pattern(q: str) -> str | None:
    m = re.match(r"^\s*(Define|Explain|Describe|State|Derive|Discuss|Prove|Compare|What is|What are|Why)\b", q, re.IGNORECASE)
    return m.group(1).title() if m else None


@mcp.tool(title="Extract PYQ style")
def extract_pyq_style(
    name: Annotated[str, Field(description="PYQ filename inside materials/pyqs/.")],
):
    """Analyze a past paper and return its structural style: question count, types, mark distribution, common stems."""
    from collections import Counter
    path = _safe_path("pyqs", name)
    if not path.exists():
        return f"No file named '{name}' in materials/pyqs/."
    text = _extract_text(path)
    if not text:
        return "Could not extract text from this file."
    questions = _parse_pyq_questions(text)
    if not questions:
        return "No questions could be parsed from this file."
    types = Counter(_classify_question(q) for q in questions)
    marks = [int(m.group(1)) for m in _MARKS_RE.finditer(text)]
    stems = Counter(s for s in (_stem_pattern(q) for q in questions) if s)
    return {
        "file": name,
        "question_count": len(questions),
        "type_breakdown": dict(types),
        "mark_distribution": sorted(marks),
        "common_stems": dict(stems.most_common(5)),
        "sample_questions": questions[:3],
    }


@mcp.tool(title="Extract PYQ questions")
def extract_pyq_questions(
    name: Annotated[str, Field(description="PYQ filename inside materials/pyqs/.")],
    max_questions: Annotated[int, Field(description="Maximum number of questions to return.", ge=1, le=100)] = 20,
):
    """Return the parsed list of actual questions from a past paper, in order."""
    path = _safe_path("pyqs", name)
    if not path.exists():
        return f"No file named '{name}' in materials/pyqs/."
    text = _extract_text(path)
    if not text:
        return []
    return _parse_pyq_questions(text)[:max_questions]


# manual file archive

@mcp.tool(title="Move files to archive")
def archive_files(
    folder: Annotated[str, Field(description="Source folder: 'content' or 'pyqs'.")],
    names: Annotated[list[str], Field(description="List of filenames to move into materials/archive/.")],
):
    """Physically move one or more files from content/ or pyqs/ into materials/archive/."""
    if folder not in {"content", "pyqs"}:
        return "Source folder must be 'content' or 'pyqs'."
    moved, missing = [], []
    for n in names:
        src = _safe_path(folder, n)
        if not src.exists():
            missing.append(n)
            continue
        dst = ARCHIVE_DIR / src.name
        shutil.move(str(src), str(dst))
        moved.append(src.name)
    return {"moved": moved, "missing": missing}


# resources

def _index_md(title: str, items: list[dict]) -> str:
    if not items:
        return f"# {title}\n\n*Empty. Drop files into this folder.*"
    lines = [f"# {title}\n"]
    for f in items:
        lines.append(f"- **{f['name']}** ({f['type']}, {f['size_kb']} KB)")
    return "\n".join(lines)


@mcp.resource("study://content")
def content_index():
    """Index of files in materials/content/."""
    return _index_md("Content files", _list_folder("content"))


@mcp.resource("study://pyqs")
def pyqs_index():
    """Index of files in materials/pyqs/."""
    return _index_md("PYQ files", _list_folder("pyqs"))


@mcp.resource("study://topics")
def topics_index():
    """Current mastery table: active topics, then archived."""
    active = list_topics(include_archived=False)
    archived = [t for t in list_topics(include_archived=True) if t["archived"]]
    lines = ["# Mastery tracker\n", "## Active topics\n"]
    if not active:
        lines.append("*No topics registered yet.*")
    for t in active:
        lines.append(f"- **{t['topic']}** at {t['mastery_pct']}% across {t['attempts']} attempts")
    lines.append("\n## Archived (mastered)\n")
    if not archived:
        lines.append("*None yet.*")
    for t in archived:
        lines.append(f"- {t['topic']} at {t['mastery_pct']}%")
    return "\n".join(lines)


# prompts

@mcp.prompt(title="Study a topic")
def study(
    topic: Annotated[str, Field(description="Topic you want to study.")],
    style: Annotated[str, Field(description="How you want it taught. Any style works: 'default', 'feynman', 'socratic', 'summary', 'eli5', 'exam-cram', or anything else you specify.")] = "default",
):
    """Teach a topic from your content in any teaching style."""
    return [
        base.UserMessage(
            f"Teach me **{topic}** using the **{style}** style.\n\n"
            "How to approach this:\n"
            f"- Locate the topic in my content files (use search_content or read_file as needed with folder='content').\n"
            "- Ground everything ONLY in what you read from my files. Do not invent material.\n"
            f"- Apply the '{style}' style. If it is a well-known one (feynman, socratic, eli5, summary, exam-cram) use that convention. Otherwise interpret the intent sensibly.\n"
            "- End by offering to quiz me on it."
        )
    ]


@mcp.prompt(title="Study everything")
def study_all(
    style: Annotated[str, Field(description="Teaching style to apply to every topic.")] = "default",
    order: Annotated[str, Field(description="'weakest_first' to prioritize low-mastery topics, or 'registered' to follow registration order.")] = "weakest_first",
):
    """Walk through every active registered topic in turn, teaching each one."""
    return [
        base.UserMessage(
            f"Teach me every active topic I have registered, one at a time, using the **{style}** style.\n\n"
            "How to approach this:\n"
            "- Call list_topics(include_archived=False) to get the active topics.\n"
            f"- If order='{order}' is 'weakest_first', sort by mastery_pct ascending; otherwise keep the returned order.\n"
            "- For each topic: search and read the relevant content files, then teach that topic in the requested style.\n"
            "- After each topic, pause and ask if I'm ready for the next one. Wait for my confirmation.\n"
            "- Skip archived topics."
        )
    ]


@mcp.prompt(title="Quiz me on a topic")
def quiz(
    topic: Annotated[str, Field(description="Topic the quiz should cover.")],
    n: Annotated[int, Field(description="How many questions?", ge=1, le=50)] = 5,
):
    """Generate a quiz drawn only from your content files."""
    return [
        base.UserMessage(
            f"Quiz me on **{topic}** with {n} questions.\n\n"
            "How to approach this:\n"
            f"- Locate '{topic}' in my content files (search_content and read_file with folder='content').\n"
            f"- Generate {n} questions grounded ONLY in what you read.\n"
            "- Ask one question at a time. Wait for my answer before continuing.\n"
            "- After each answer, tell me if it's correct and give a short explanation.\n"
            f"- At the end, call log_result with topic='{topic}', score=<correct>, total={n}.\n"
            f"- If log_result reports the topic isn't registered, call register_topic with name='{topic}' first, then retry."
        )
    ]


@mcp.prompt(title="PYQ test")
def pyq_test(
    topic: Annotated[str, Field(description="Topic the test should cover.")],
    mode: Annotated[str, Field(description="'ask' to let the user choose, 'verbatim' for real PYQ questions, or 'style' for new questions in PYQ style.")] = "ask",
    n: Annotated[int, Field(description="How many questions?", ge=1, le=50)] = 5,
):
    """Test on past-paper questions: real ones, or new ones in the same style."""
    return [
        base.UserMessage(
            f"PYQ test on **{topic}** with {n} questions. Mode: **{mode}**.\n\n"
            "How to approach this:\n"
            "- Call list_pyqs to see available past papers and pick the ones most relevant to the topic.\n"
            "- If mode='ask', ask me whether I want VERBATIM (real past questions) or STYLE (new questions in that style). Wait for my answer.\n"
            "- For VERBATIM: use extract_pyq_questions on the relevant paper(s), filter to the topic, "
            f"and pick {n}. Ask one at a time and grade each answer.\n"
            "- For STYLE: use extract_pyq_style on the relevant paper(s) to get the structural profile, "
            f"then search and read my content files, then generate {n} NEW questions that match the extracted style "
            "(types, mark distribution, common stems) grounded in my content. Ask one at a time and grade.\n"
            f"- At the end, call log_result with topic='{topic}', score=<correct>, total={n}.\n"
            f"- If log_result reports the topic isn't registered, call register_topic with name='{topic}' first, then retry."
        )
    ]


if __name__ == "__main__":
    mcp.run()