#!/usr/bin/env python3
"""fetch-chunks.py — Fetch ALL Lenx task data through lenx-mcp, filter fields, and write compact TOON chunks.

TOON (Tab-delimited, Token-Optimized Notation) keeps only relevant fields,
truncates long messages, and uses tab separation — ~60-70% smaller than raw JSON.

Resumable: detects existing chunk files and continues from where it left off.
Fetches pages through the lenx_get_task_data MCP tool using max API page size
(1000) for speed.
Writes chunk files with dynamic sizing (default ~100 KB each) so each subagent
gets a similar workload regardless of post length.

Usage:
    python3 fetch-chunks.py <task-id> <from-epoch-seconds> <to-epoch-seconds> [target-kb] [output-dir]

Environment:
    LENX_API_KEY and LENX_USER_ID are required by @fastaai/lenx-mcp.
    LENX_BASE_URL is optional.
    LENX_MCP_COMMAND optionally overrides the stdio server command
    (default: npx -y @fastaai/lenx-mcp).

Output (three lines to stdout):
    Line 1: TOTAL_RECORDS  — total from API
    Line 2: TOTAL_CHUNKS   — number of chunk files written so far
    Line 3: COMPLETE       — "yes" if all records fetched, "no" if incomplete

Can be re-run safely — skips already-fetched data automatically.
"""
import glob
import json
import os
import select
import shlex
import subprocess
import sys
import time

FETCH_PAGE_SIZE = 1000  # max API allows
MAX_RETRIES = 3
RETRY_DELAY = 2
DEFAULT_TARGET_KB = 100  # ~25 K tokens — fits comfortably in 128 K context
RPC_TIMEOUT_SECONDS = 120
MCP_PROTOCOL_VERSION = "2024-11-05"

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

_MCP_CLIENT = None


# ── MCP stdio client ─────────────────────────────────────────────────────

def lenx_mcp_command():
    """Return the command used to start the lenx-mcp stdio server."""
    override = os.environ.get("LENX_MCP_COMMAND")
    if override:
        return shlex.split(override)
    return ["npx", "-y", "@fastaai/lenx-mcp"]


class LenxMcpClient:
    """Minimal MCP stdio client for @fastaai/lenx-mcp.

    MCP stdio uses newline-delimited JSON-RPC messages. This client performs
    the initialize/initialized handshake and calls tools/call for
    lenx_get_task_data.
    """

    def __init__(self):
        self.proc = None
        self.next_id = 1

    def start(self):
        missing = [name for name in ("LENX_API_KEY", "LENX_USER_ID") if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        command = lenx_mcp_command()
        try:
            self.proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Unable to start lenx-mcp stdio server: {command[0]} not found. "
                "Install Node.js/npx or set LENX_MCP_COMMAND to a lenx-mcp command."
            ) from exc

        init_result = self.rpc(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "lenx-task-summariser", "version": "1.2"},
            },
        )
        server_info = init_result.get("serverInfo", {})
        server_name = server_info.get("name", "lenx-mcp")
        print(f"  Connected to {server_name} stdio server", file=sys.stderr)
        self.notify("notifications/initialized", {})

    def send(self, message):
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("lenx-mcp stdio server is not running")
        self.proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def recv(self, timeout=RPC_TIMEOUT_SECONDS):
        if self.proc is None or self.proc.stdout is None:
            raise RuntimeError("lenx-mcp stdio server is not running")

        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(f"Timed out waiting {timeout}s for lenx-mcp response")

        line = self.proc.stdout.readline()
        if not line:
            code = self.proc.poll()
            raise RuntimeError(f"lenx-mcp stdio server stopped unexpectedly (exit {code})")

        line = line.strip()
        if not line:
            return self.recv(timeout)
        return json.loads(line)

    def rpc(self, method, params):
        msg_id = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})

        while True:
            message = self.recv()
            if message.get("id") != msg_id:
                continue
            if "error" in message:
                raise RuntimeError(f"MCP {method} failed: {message['error']}")
            return message.get("result", {})

    def notify(self, method, params):
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def call_tool(self, name, arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        text = "\n".join(part for part in text_parts if part)

        if result.get("isError"):
            raise RuntimeError(f"MCP tool {name} failed: {text or result}")
        if not text:
            raise RuntimeError(f"MCP tool {name} returned no text content")
        return json.loads(text)

    def close(self):
        if self.proc is None:
            return
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except Exception:
                self.proc.kill()
        finally:
            self.proc = None


def get_mcp_client():
    """Start and cache a single lenx-mcp stdio process for this script run."""
    global _MCP_CLIENT
    if _MCP_CLIENT is None:
        client = LenxMcpClient()
        try:
            client.start()
        except Exception:
            client.close()
            raise
        _MCP_CLIENT = client
    return _MCP_CLIENT


def close_mcp_client():
    global _MCP_CLIENT
    if _MCP_CLIENT is not None:
        _MCP_CLIENT.close()
        _MCP_CLIENT = None


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

def fetch_page(task_id, from_ts, to_ts, size, search_after=None):
    """Call lenx_get_task_data via lenx-mcp and return parsed JSON. Retries on failure."""
    arguments = {
        "task_id": int(task_id),
        "from": int(from_ts),
        "to": int(to_ts),
        "size": int(size),
    }
    if search_after is not None:
        arguments["search_after"] = int(search_after)

    delay = RETRY_DELAY
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = get_mcp_client().call_tool("lenx_get_task_data", arguments)
            if "data" in resp:
                return resp
            last_error = RuntimeError("response did not include a data field")
        except (TimeoutError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
            last_error = exc
            close_mcp_client()

        if attempt < MAX_RETRIES - 1:
            print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {delay}s...", file=sys.stderr)
            time.sleep(delay)
            delay *= 2

    detail = f": {last_error}" if last_error else ""
    print(f"FETCH_FAILED after {MAX_RETRIES} attempts{detail}", file=sys.stderr)
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
    from_ts = sys.argv[2]
    to_ts = sys.argv[3]
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
        resp = fetch_page(task_id, from_ts, to_ts, FETCH_PAGE_SIZE)
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
        resp = fetch_page(task_id, from_ts, to_ts, 1)
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
        resp = fetch_page(task_id, from_ts, to_ts, FETCH_PAGE_SIZE, search_after)
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
    try:
        main()
    finally:
        close_mcp_client()
