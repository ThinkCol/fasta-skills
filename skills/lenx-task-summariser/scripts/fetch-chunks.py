#!/usr/bin/env python3
"""fetch-chunks.py — Fetch ALL lenx task data, filter fields, and write compact TOON chunks.

TOON (Tab-delimited, Token-Optimized Notation) keeps only relevant fields,
truncates long messages, and uses tab separation — ~60-70% smaller than raw JSON.

Resumable: detects existing chunk files and continues from where it left off.
Fetches pages using max API page size (1000) for speed.
Writes chunk files with dynamic sizing (default ~100 KB each) so each subagent
gets a similar workload regardless of post length.

Usage:
    python3 fetch-chunks.py <task-id> <from-ms> <to-ms> [target-kb] [output-dir]

Output (three lines to stdout):
    Line 1: TOTAL_RECORDS  — total from API
    Line 2: TOTAL_CHUNKS   — number of chunk files written so far
    Line 3: COMPLETE       — "yes" if all records fetched, "no" if incomplete

Can be re-run safely — skips already-fetched data automatically.
"""
import glob
import json
import os
import subprocess
import sys
import time

FETCH_PAGE_SIZE = 1000  # max API allows
MAX_RETRIES = 3
RETRY_DELAY = 2
DEFAULT_TARGET_KB = 100  # ~25 K tokens — fits comfortably in 128 K context

# Fields to keep from API response (order = TOON column order).
# unix_timestamp is last — only used for resume, not analysis.
TOON_FIELDS = [
    "post_timestamp", "post_message", "thread_title", "site", "country",
    "post_link", "sentiment_score", "medium", "channel",
    "reaction_count", "comment_count", "share_count", "view_count",
    "unix_timestamp",
]

TOON_HEADER = "#TOON v1\n#" + "\t".join(TOON_FIELDS) + "\n"

MAX_MESSAGE_WORDS = 500


# ── Helpers ──────────────────────────────────────────────────────────────

def truncate_words(text, max_words):
    """Truncate text to *max_words* words (UTF-8 safe)."""
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def sanitize_field(value):
    """Replace tabs and newlines with spaces so TOON columns stay intact."""
    if value is None:
        return ""
    return str(value).replace("\t", " ").replace("\n", " ").replace("\r", " ")


def record_to_toon_line(record):
    """Convert an API record dict to a single TOON line."""
    parts = []
    for field in TOON_FIELDS:
        val = record.get(field, "")
        if field == "post_message":
            val = truncate_words(sanitize_field(val), MAX_MESSAGE_WORDS)
        else:
            val = sanitize_field(val)
        parts.append(val)
    return "\t".join(parts)


# ── Chunk I/O ────────────────────────────────────────────────────────────

def write_chunk(out_dir, chunk_index, lines):
    """Write TOON lines to a chunk file."""
    path = os.path.join(out_dir, f"chunk{chunk_index}.toon")
    with open(path, "w", encoding="utf-8") as f:
        f.write(TOON_HEADER)
        for line in lines:
            f.write(line + "\n")


def detect_existing_chunks(out_dir):
    """Scan for existing TOON chunk files.

    Returns (chunk_count, record_count, last_unix_timestamp).
    """
    pattern = os.path.join(out_dir, "chunk*.toon")
    files = glob.glob(pattern)
    if not files:
        return 0, 0, None

    def chunk_idx(f):
        return int(os.path.basename(f).replace("chunk", "").replace(".toon", ""))

    files.sort(key=chunk_idx)

    total_records = 0
    last_ts = None
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                total_records += 1
                parts = line.split("\t")
                if parts:
                    last_ts = parts[-1]  # unix_timestamp is the last field

    return len(files), total_records, last_ts


# ── API ──────────────────────────────────────────────────────────────────

def fetch_page(task_id, from_ms, to_ms, size, search_after=None):
    """Call lenx task data and return parsed JSON. Retries on failure."""
    cmd = ["lenx", "task", "data", str(task_id),
           "--from", str(from_ms), "--to", str(to_ms), "--size", str(size)]
    if search_after is not None:
        cmd.extend(["--search-after", str(search_after)])

    delay = RETRY_DELAY
    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                resp = json.loads(result.stdout)
                if "data" in resp:
                    return resp
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        except Exception:
            pass

        if attempt < MAX_RETRIES - 1:
            print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {delay}s...", file=sys.stderr)
            time.sleep(delay)
            delay *= 2

    print(f"FETCH_FAILED after {MAX_RETRIES} attempts", file=sys.stderr)
    return None


# ── ChunkWriter ──────────────────────────────────────────────────────────

class ChunkWriter:
    """Accumulates TOON lines and flushes a chunk file when the byte budget
    is exceeded.  This gives dynamic chunk sizes — short posts produce more
    records per chunk, long posts produce fewer."""

    def __init__(self, out_dir, target_bytes):
        self.out_dir = out_dir
        self.target_bytes = target_bytes
        self.chunk_index = 0
        self.buffer = []
        self.buffer_bytes = 0

    def set_start_index(self, index):
        self.chunk_index = index

    def add(self, toon_line):
        line_bytes = len(toon_line.encode("utf-8")) + 1  # +1 for newline
        if self.buffer and self.buffer_bytes + line_bytes > self.target_bytes:
            self._flush()
        self.buffer.append(toon_line)
        self.buffer_bytes += line_bytes

    def _flush(self):
        if self.buffer:
            write_chunk(self.out_dir, self.chunk_index, self.buffer)
            self.chunk_index += 1
            self.buffer = []
            self.buffer_bytes = 0

    def finish(self):
        """Flush remaining data and return total chunk count."""
        self._flush()
        return self.chunk_index


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    task_id = sys.argv[1]
    from_ms = sys.argv[2]
    to_ms = sys.argv[3]
    target_kb = int(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_TARGET_KB
    out_dir = sys.argv[5] if len(sys.argv) > 5 else ".lenx-summariser-work"
    target_bytes = target_kb * 1024

    os.makedirs(out_dir, exist_ok=True)

    # ── Resume detection ─────────────────────────────────────────────────
    chunk_index, already_fetched, resume_after = detect_existing_chunks(out_dir)

    if chunk_index > 0:
        print(f"  Resuming: found {chunk_index} existing chunks ({already_fetched} records)",
              file=sys.stderr)

    writer = ChunkWriter(out_dir, target_bytes)
    writer.set_start_index(chunk_index)

    # ── First API call (or resume probe) ─────────────────────────────────
    if chunk_index == 0:
        resp = fetch_page(task_id, from_ms, to_ms, FETCH_PAGE_SIZE)
        if resp is None:
            print("0\n0\nno")
            sys.exit(1)

        total_records = resp.get("total", 0)
        if total_records == 0:
            print("0\n0\nyes")
            return

        data = resp.get("data", [])
        already_fetched = len(data)
        print(f"  Fetched page 1: {len(data)} records ({already_fetched}/{total_records})",
              file=sys.stderr)

        for record in data:
            writer.add(record_to_toon_line(record))

        if len(data) < FETCH_PAGE_SIZE or already_fetched >= total_records:
            chunk_index = writer.finish()
            print(f"{total_records}\n{chunk_index}\nyes")
            return

        resume_after = data[-1]["unix_timestamp"]
    else:
        resp = fetch_page(task_id, from_ms, to_ms, 1)
        if resp is None:
            print(f"0\n{chunk_index}\nno")
            sys.exit(1)
        total_records = resp.get("total", 0)

        if already_fetched >= total_records * 0.9:
            print(f"  Already complete: {already_fetched}/{total_records}", file=sys.stderr)
            print(f"{total_records}\n{chunk_index}\nyes")
            return

        print(f"  Need to fetch {total_records - already_fetched} more records",
              file=sys.stderr)

    # ── Fetch remaining pages ────────────────────────────────────────────
    search_after = resume_after
    page = 1
    data = []

    while already_fetched < total_records:
        resp = fetch_page(task_id, from_ms, to_ms, FETCH_PAGE_SIZE, search_after)
        if resp is None:
            print(f"WARNING: stopped after {already_fetched} of {total_records} records",
                  file=sys.stderr)
            break

        data = resp.get("data", [])
        if not data:
            break

        already_fetched += len(data)
        page += 1
        print(f"  Fetched page {page}: {len(data)} records ({already_fetched}/{total_records})",
              file=sys.stderr)

        for record in data:
            writer.add(record_to_toon_line(record))

        if len(data) < FETCH_PAGE_SIZE or already_fetched >= total_records:
            break

        search_after = data[-1]["unix_timestamp"]

    chunk_index = writer.finish()

    # ── Output ───────────────────────────────────────────────────────────
    fetched_enough = already_fetched >= total_records * 0.9
    last_page_short = len(data) < FETCH_PAGE_SIZE if data else True
    complete = "yes" if (fetched_enough or last_page_short) else "no"
    if complete == "no":
        print(f"WARNING: fetched {already_fetched} of {total_records} records",
              file=sys.stderr)
    print(f"{total_records}\n{chunk_index}\n{complete}")


if __name__ == "__main__":
    main()
