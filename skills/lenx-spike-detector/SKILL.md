---
name: lenx-spike-detector
description: "Detect activity spikes in Lenx task monitoring data via the lenx-mcp stdio server. Use when asked to find spikes, detect anomalies, sudden increases, surges, or bursts in social media monitoring data — including volume spikes, sentiment spikes (e.g. surge in negative posts), engagement spikes, and topic spikes. Triggers on: /lenx-spikes, detect spikes, activity spike, sentiment spike, volume spike, engagement spike, spike in task, find anomalies in task."
compatibility: "Requires the MCP client/agent to have lenx-mcp stdio configured so the lenx_get_task_data MCP tool is available. Requires Python 3. Chart generation requires matplotlib; topic auto-discovery for Chinese text benefits from jieba (optional)."
metadata:
  author: thinkcol
  version: "1.0"
---

# Lenx Task Spike Detector

You MUST follow every step below in exact order. Do NOT skip steps. Do NOT improvise. Do NOT add your own logic. Execute each step literally, then move to the next.

## Step 1 — Parse the user prompt

Extract these values from the user's message. Do not ask clarifying questions unless Task ID is missing.

| Variable | How to extract | Default |
|---|---|---|
| `TASK_ID` | Number after "task" (e.g., `task 1528` → `1528`) | **Required** — ask if missing |
| `TIME_RANGE` | "past 24 hours", "last 7 days", "from X to Y", etc. | `past 24 hours` |
| `TOPIC` | `--topic "kw1,kw2"` or `topic kw1 and kw2` | Empty (auto-discover top spiking topics) |
| `SENTIMENT` | `--sentiment negative\|positive\|neutral` | `negative` |
| `METRICS` | `--metrics all` or comma-list from volume,sentiment,engagement,topic | `all` |
| `SENSITIVITY` | `--sensitivity N` | `3.0` |
| `BUCKET` | `--bucket auto\|hourly\|6h\|daily` | `auto` |
| `MAX_TOPICS` | `--max-topics N` | `15` |
| `FORMAT` | `--format markdown\|text` (also `--markdown`/`--text`) | `markdown` |
| `NO_CHART` | `--no-chart` flag | `false` (chart generated) |

Set this constant — do NOT change it:

```
WORK_DIR=".lenx-spikes-work"
```

Resolve `SKILL_DIR` to the absolute path of this skill's directory (the directory containing this SKILL.md file).

Proceed to Step 2.

## Step 2 — Check prerequisites

Confirm the current agent has access to the `lenx_get_task_data` MCP tool from a configured `lenx-mcp` stdio server.

Do NOT ask the user for `LENX_API_KEY`, `LENX_USER_ID`, or `LENX_BASE_URL`. Those credentials belong in the user's MCP client configuration and are used by the already-configured `lenx-mcp` server.

If `lenx_get_task_data` is not available, tell the user: "The lenx-mcp stdio server is not available in this MCP client. Please configure `@fastaai/lenx-mcp` in your `mcpServers` settings, then restart/reload the client." Then STOP. Do not continue.

If a chart is requested (`NO_CHART` is false) and `matplotlib` is not installed, either tell the user: "matplotlib is required for chart generation. Install it with `pip install matplotlib`, or rerun with `--no-chart`." and STOP, or proceed with `--no-chart` if the user agrees.

Otherwise proceed to Step 3.

## Step 3 — Calculate timestamps

lenx-mcp expects `from`, `to`, and `search_after` as Unix timestamp **milliseconds**. Do NOT use seconds.

Run the appropriate command based on `TIME_RANGE`:

```bash
# Past 24 hours
FROM_MS=$(python3 -c "import time; print(int((time.time() - 86400) * 1000))")
TO_MS=$(python3 -c "import time; print(int(time.time() * 1000))")
```

```bash
# Past 7 days
FROM_MS=$(python3 -c "import time; print(int((time.time() - 604800) * 1000))")
TO_MS=$(python3 -c "import time; print(int(time.time() * 1000))")
```

```bash
# Past 30 days
FROM_MS=$(python3 -c "import time; print(int((time.time() - 2592000) * 1000))")
TO_MS=$(python3 -c "import time; print(int(time.time() * 1000))")
```

```bash
# Custom range — replace DATE_FROM and DATE_TO with ISO dates
FROM_MS=$(python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('DATE_FROM').timestamp() * 1000))")
TO_MS=$(python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('DATE_TO').timestamp() * 1000))")
```

Also calculate a human-readable date string for the output filename:

```bash
FROM_DATE=$(python3 -c "from datetime import datetime; print(datetime.fromtimestamp($FROM_MS / 1000).strftime('%Y%m%d'))")
TO_DATE=$(python3 -c "from datetime import datetime; print(datetime.fromtimestamp($TO_MS / 1000).strftime('%Y%m%d'))")
```

You now have `FROM_MS`, `TO_MS`, `FROM_DATE`, and `TO_DATE`. Proceed to Step 4.

## Step 4 — Fetch ALL data into JSONL via MCP

**YOU — the main agent — MUST NOT fetch pages yourself.** Raw MCP page results can be large and will pollute your context. Dispatch exactly one fetch subagent to do the MCP pagination using the tool's direct-to-disk `output_path` parameter, then convert the resulting JSONL to TSV.

**4A — Create work directory**

```bash
mkdir -p .lenx-spikes-work
```

**4B — Dispatch fetch subagent**

Call the Task tool once with this prompt. Replace `{TASK_ID}`, `{FROM_MS}`, and `{TO_MS}`:

```
Use the configured lenx-mcp stdio MCP tool `lenx_get_task_data` to fetch all Lenx monitoring data for task {TASK_ID} from Unix timestamp milliseconds {FROM_MS} to {TO_MS}.

Do not ask for Lenx credentials. They are already configured in the MCP client. Do not return raw records in your final response.

The `lenx_get_task_data` tool supports an `output_path` parameter that writes results as JSONL directly to disk, avoiding large response payloads in your context.

Fetch pages using these arguments:
- task_id: {TASK_ID}
- from: {FROM_MS}
- to: {TO_MS}
- size: 1000
- output_path: .lenx-spikes-work/all_posts.jsonl

For the FIRST page, use output_mode: "overwrite" (creates a fresh file).
For each subsequent page, use output_mode: "append" (adds to the existing file).
- search_after: omit on the first call; for later calls, use the `unix_timestamp` millisecond value of the last record from the previous page

The tool auto-appends .jsonl if the path doesn't end with it, so the actual file will be all_posts.jsonl.

Retry failed MCP tool calls up to 3 times with exponential backoff (2s, 4s, 8s). Continue until all available pages are fetched (fetched >= total) or the last page has fewer than 1000 records.

When done, write `.lenx-spikes-work/fetch_metadata.json` with exactly:
{
  "total_records": <total from lenx_get_task_data>,
  "complete": true
}

Final response: one sentence only, with total records and the filename. Do not include raw records.
```

Wait until the fetch subagent returns.

**4C — Verify fetch completed**

Run this command:

```bash
python3 - <<'PY'
import json
with open('.lenx-spikes-work/fetch_metadata.json', 'r', encoding='utf-8') as f:
    meta = json.load(f)
print(meta['total_records'])
print('yes' if meta.get('complete') else 'no')
PY
```

Assign stdout line 1 to `TOTAL_RECORDS`, line 2 to `COMPLETE`.

If `COMPLETE` is not `yes`, STOP and report that data fetching did not complete.

If `TOTAL_RECORDS` is `0`, tell the user "No data found for task {TASK_ID} in the specified time range" and STOP.

**4D — Convert JSONL to TSV**

Run this command to extract the fields `detect_spikes.py` needs (`unix_timestamp`, `post_message`, `ai_sentiment`, `sentiment_score`, `reaction_count`, `comment_count`, `share_count`, `view_count`, `lang_abbr`, `site`, `post_link`, `thread_title`) from the JSONL into the TSV format that detect_spikes.py expects:

```bash
python3 - <<'PY'
import json

jsonl_path = '.lenx-spikes-work/all_posts.jsonl'
tsv_path = '.lenx-spikes-work/posts.tsv'
columns = ['unix_timestamp', 'post_message', 'ai_sentiment', 'sentiment_score',
           'reaction_count', 'comment_count', 'share_count', 'view_count',
           'lang_abbr', 'site', 'post_link', 'thread_title']
count = 0

def to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0

def clean(value):
    return str(value).replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')

with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as inf, \
     open(tsv_path, 'w', encoding='utf-8') as outf:
    outf.write('#' + '\t'.join(columns) + '\n')
    for line in inf:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        message = clean(record.get('post_message', ''))
        words = message.split()
        if len(words) > 500:
            message = ' '.join(words[:500])

        fields = [
            str(to_int(record.get('unix_timestamp', 0))),
            message,
            clean(record.get('ai_sentiment', '')),
            clean(record.get('sentiment_score', '')),
            str(to_int(record.get('reaction_count', 0))),
            str(to_int(record.get('comment_count', 0))),
            str(to_int(record.get('share_count', 0))),
            str(to_int(record.get('view_count', 0))),
            clean(record.get('lang_abbr', '')),
            clean(record.get('site', '')),
            clean(record.get('post_link', '')),
            clean(record.get('thread_title', '')),
        ]
        outf.write('\t'.join(fields) + '\n')
        count += 1

print(f"Converted {count} records")
PY
```

Verify the posts file exists:
```bash
wc -l .lenx-spikes-work/posts.tsv
```

The line count should equal `TOTAL_RECORDS` + 1 (the extra line is the `#` header). Alternatively, verify the converter printed `Converted <TOTAL_RECORDS> records`. Proceed to Step 5.

## Step 5 — Run spike detection

Run this exact command. Substitute all `{}` variables.

```bash
python3 "SKILL_DIR/scripts/detect_spikes.py" \
  --input ".lenx-spikes-work/posts.tsv" \
  --from-ms {FROM_MS} \
  --to-ms {TO_MS} \
  --task-id {TASK_ID} \
  --report ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}" \
  --chart ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.png" \
  --metadata ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.json" \
  --metrics {METRICS} \
  --sentiment {SENTIMENT} \
  --sensitivity {SENSITIVITY} \
  --bucket {BUCKET} \
  --max-topics {MAX_TOPICS} \
  --format {FORMAT} \
  {TOPIC_FLAG} \
  {NO_CHART_FLAG}
```

Where:
- `TOPIC_FLAG` is `--topic "kw1,kw2"` if `TOPIC` is set, else empty string
- `NO_CHART_FLAG` is `--no-chart` if `NO_CHART` is true, else empty string

The script auto-appends `.md` or `.txt` to the `--report` path based on `--format`.

Verify the output files exist:

```bash
ls -la ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.{FORMAT_EXT}"
ls -la ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.png"
ls -la ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.json"
```

Where `FORMAT_EXT` is `md` when `FORMAT` is `markdown`, `txt` when `FORMAT` is `text`. Skip the `.png` check if `NO_CHART` is true. If the `.png` is absent but the script printed `Chart: skipped ...`, treat this run as if `NO_CHART` were true (skip the chart copy in Step 6).

Proceed to Step 6.

## Step 6 — Copy outputs to working directory

```bash
cp ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.{FORMAT_EXT}" "./spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.{FORMAT_EXT}"
cp ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.json" "./spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.json"
```

If a chart was generated (skip if `NO_CHART` is true):

```bash
cp ".lenx-spikes-work/spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.png" "./spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.png"
```

Set `OUTPUT_REPORT` to `./spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.{FORMAT_EXT}`.
Set `OUTPUT_META` to `./spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.json`.
Set `OUTPUT_CHART` to `./spikes_task_{TASK_ID}_{FROM_DATE}_{TO_DATE}.png` if a chart was generated, otherwise `none`.

Proceed to Step 7.

## Step 7 — Cleanup

```bash
rm -rf .lenx-spikes-work
```

Verify cleanup:
```bash
ls .lenx-spikes-work 2>/dev/null && echo "ERROR: work dir still exists" || echo "cleanup OK"
```

After this, the ONLY files remaining are `OUTPUT_REPORT`, `OUTPUT_CHART` (if generated), and `OUTPUT_META`.

Proceed to Step 8.

## Step 8 — Respond to user

Read the metadata JSON file:

```bash
python3 - <<'PY'
import json
with open('OUTPUT_META', 'r', encoding='utf-8') as f:
    meta = json.load(f)
# Pretty-print
print(json.dumps(meta, indent=2, ensure_ascii=False))
PY
```

Substitute `OUTPUT_META` with the actual file path.

Say exactly three things:

1. **File path(s):** "Spike report saved to: `{OUTPUT_REPORT}`" and "Spike chart saved to: `{OUTPUT_CHART}`" (or "No chart generated" if `OUTPUT_CHART` is `none`).
2. **Summary:** Present a concise summary from the metadata — bucket size used, total records, number of spikes detected per metric, and the most notable spike(s) with time + magnitude.
3. **Metadata:** "Task {TASK_ID} | {TIME_RANGE} | {TOTAL_RECORDS} records | bucket: {bucket} | sensitivity: {SENSITIVITY} | metrics: {METRICS}"

Do NOT mention chunks, subagents, MCP pagination, or any internal process.

**DONE.** Do not continue past this step.

---

## Reference — lenx-mcp stdio configuration

This skill expects the user's MCP client to expose the `lenx_get_task_data` tool from a configured `lenx-mcp` stdio server. Example MCP client configuration:

```json
{
  "mcpServers": {
    "lenx": {
      "command": "npx",
      "args": ["-y", "@fastaai/lenx-mcp"],
      "env": {
        "LENX_API_KEY": "your-api-key",
        "LENX_USER_ID": "your-user-id",
        "LENX_BASE_URL": "https://open.lenx.ai"
      }
    }
  }
}
```

Credential handling:
- Do not ask the user to re-enter credentials if `lenx_get_task_data` is already available.
- Do not read MCP config files to extract credentials.
- Do not log or copy credential values into generated files.

Only the `lenx_get_task_data` MCP tool is required by this skill.

## Reference — Spike detection parameters

| Flag | Default | Description |
|---|---|---|
| `--metrics` | `all` | Comma-list from `volume,sentiment,engagement,topic` (or `all`) |
| `--sentiment` | `negative` | Target sentiment for the sentiment metric: `negative`, `positive`, or `neutral` |
| `--sensitivity` | `3.0` | Robust-z threshold for a bucket to count as a spike |
| `--bucket` | `auto` | Bucket size: `auto` (adaptive), `hourly`, `6h`, or `daily` |
| `--max-topics` | `15` | Maximum terms considered for topic auto-discovery |
| `--format` | `markdown` | Report format: `markdown` or `text` |
| `--topic` | empty | Comma-separated keywords to track for the topic metric (empty = auto-discover) |
| `--no-chart` | `false` | Skip PNG chart generation |
| `--stopwords` | bundled stopwords_en.txt (auto-resolved next to the script) | Optional stopword file for topic auto-discovery |

## Reference — Example walkthrough

| Step | Action | Result |
|---|---|---|
| 1 | Parse: `TASK_ID=1528`, `TIME_RANGE="past 7 days"`, `TOPIC="delivery"`, `SENTIMENT="negative"` | Variables set |
| 2 | Confirm `lenx_get_task_data` available | OK |
| 3 | Run 7-day timestamp commands | `FROM_MS`, `TO_MS`, `FROM_DATE`, `TO_DATE` set |
| 4 | Create `.lenx-spikes-work`, dispatch fetch subagent, verify `fetch_metadata.json`, convert JSONL → `posts.tsv` | `posts.tsv` with `TOTAL_RECORDS` lines |
| 5 | Run `detect_spikes.py` with `--topic delivery --sentiment negative` | Report, chart, metadata JSON written |
| 6 | Copy outputs to `./` | `OUTPUT_REPORT`, `OUTPUT_CHART`, `OUTPUT_META` set |
| 7 | `rm -rf .lenx-spikes-work` | Work dir gone |
| 8 | Read metadata, respond with paths + summary | Done |

## STRICT — Rules you MUST NOT break

1. Follow Steps 1–8 in exact order. Do not skip. Do not reorder. Do not add steps.
2. **YOU (the main agent) MUST dispatch the fetch subagent in Step 4.** Do NOT fetch MCP data yourself.
3. NEVER read raw MCP page results yourself. Always delegate to the subagent.
4. ALWAYS clean up `.lenx-spikes-work` before responding. The only artifacts are the report, chart, and metadata files.
5. If the fetch subagent fails, re-dispatch it. Do not restart the entire process.
6. Do NOT stop early. Complete ALL steps through Step 8.
