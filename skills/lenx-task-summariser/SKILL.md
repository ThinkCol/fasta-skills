---
name: lenx-task-summariser
description: "Summarise Lenx task monitoring data from the lenx-mcp stdio server using recursive hierarchical summarisation. Use when asked to summarise, analyse, or report on lenx task data, especially large datasets. Triggers on: /lenx-summarise, lenx summary, lenx report, summarise lenx task, lenx task analysis."
compatibility: "Requires the MCP client/agent to have lenx-mcp stdio configured so the lenx_get_task_data MCP tool is available. Requires Python 3 and bash."
metadata:
  author: thinkcol
  version: "1.3"
---

# Lenx Task Data Summariser

You MUST follow every step below in exact order. Do NOT skip steps. Do NOT improvise. Do NOT add your own logic. Execute each step literally, then move to the next.

## Step 1 — Parse the user prompt

Extract these values from the user's message. Do not ask clarifying questions unless Task ID is missing.

| Variable | How to extract | Default |
|---|---|---|
| `TASK_ID` | Number after "task" (e.g., `task 1528` → `1528`) | **Required** — ask if missing |
| `TIME_RANGE` | "past 24 hours", "last 7 days", "from X to Y", etc. | `past 24 hours` |
| `USER_FOCUS` | Everything describing what to focus on (e.g., "negative sentiment", "complaints about delivery") | Empty string (summarise everything) |
| `FORMAT` | `--text` → `text`, `--markdown` → `markdown`, `--email` → `email` | `markdown` |
| `PARALLEL_CAP` | `--parallel N` → `N` | `5` |
| `CHUNK_KB` | `--chunk-kb N` → `N` (target kilobytes per chunk file) | `100` |

Set these constants — do NOT change them:

```
WORK_DIR=".lenx-summariser-work"
MERGE_GROUP_SIZE=5
```

Resolve `SKILL_DIR` to the absolute path of this skill's directory (the directory containing this SKILL.md file).

Proceed to Step 2.

## Step 2 — Check prerequisites

Confirm the current agent has access to the `lenx_get_task_data` MCP tool from a configured `lenx-mcp` stdio server.

Do NOT ask the user for `LENX_API_KEY`, `LENX_USER_ID`, or `LENX_BASE_URL`. Those credentials belong in the user's MCP client configuration and are used by the already-configured `lenx-mcp` server.

If `lenx_get_task_data` is not available, tell the user: "The lenx-mcp stdio server is not available in this MCP client. Please configure `@fastaai/lenx-mcp` in your `mcpServers` settings, then restart/reload the client." Then STOP. Do not continue.

Otherwise proceed to Step 3.

## Step 3 — Calculate timestamps

lenx-mcp expects `from` and `to` as Unix epoch **seconds**. Do NOT use milliseconds.

Run the appropriate command based on `TIME_RANGE`:

```bash
# Past 24 hours
FROM_TS=$(python3 -c "import time; print(int(time.time() - 86400))")
TO_TS=$(python3 -c "import time; print(int(time.time()))")
```

```bash
# Past 7 days
FROM_TS=$(python3 -c "import time; print(int(time.time() - 604800))")
TO_TS=$(python3 -c "import time; print(int(time.time()))")
```

```bash
# Past 30 days
FROM_TS=$(python3 -c "import time; print(int(time.time() - 2592000))")
TO_TS=$(python3 -c "import time; print(int(time.time()))")
```

```bash
# Custom range — replace DATE_FROM and DATE_TO with ISO dates
FROM_TS=$(python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('DATE_FROM').timestamp()))")
TO_TS=$(python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('DATE_TO').timestamp()))")
```

You now have `FROM_TS` and `TO_TS`. Proceed to Step 4.

## Step 4 — Fetch ALL data into chunks

**YOU — the main agent — MUST NOT fetch pages yourself.** Raw MCP page results can be large and will pollute your context. Dispatch exactly one fetch subagent to do the MCP pagination and chunk writing, then only read the small metadata file it creates.

**4A — Dispatch fetch subagent**

Call the Task tool once with this prompt. Replace `{TASK_ID}`, `{FROM_TS}`, `{TO_TS}`, and `{CHUNK_KB}`:

```
Use the configured lenx-mcp stdio MCP tool `lenx_get_task_data` to fetch all Lenx monitoring data for task {TASK_ID} from Unix epoch second {FROM_TS} to {TO_TS}.

Do not ask for Lenx credentials. They are already configured in the MCP client. Do not return raw records in your final response.

Fetch pages with arguments:
- task_id: {TASK_ID}
- from: {FROM_TS}
- to: {TO_TS}
- size: 1000
- search_after: omit on the first call; for later calls, use the `unix_timestamp` of the last record from the previous page

For each page, immediately convert records to compact TOON files under `.lenx-summariser-work`:
- Create `.lenx-summariser-work` if it does not exist before writing files
- Keep fields in this order: post_timestamp, post_message, thread_title, site, country, post_link, sentiment_score, medium, channel, reaction_count, comment_count, share_count, view_count, unix_timestamp
- Replace tabs/newlines/carriage returns in field values with spaces
- Truncate `post_message` to 500 words
- Write `#TOON v1` then a `#` header line with the field names joined by tabs
- Dynamically size files to about {CHUNK_KB} KB each, named `chunk0.toon`, `chunk1.toon`, etc.

Retry failed MCP tool calls up to 3 times with exponential backoff (2s, 4s, 8s). Continue until all available pages are fetched (`fetched >= total`) or the last page has fewer than 1000 records.

When done, write `.lenx-summariser-work/fetch_metadata.json` with exactly:
{
  "total_records": <total from lenx_get_task_data>,
  "total_chunks": <number of chunk*.toon files>,
  "complete": true
}

Final response: one sentence only, with total records and total chunks. Do not include raw records.
```

Wait until the fetch subagent returns.

**4B — Read fetch metadata:**

Run this exact command:

```bash
python3 - <<'PY'
import json
with open('.lenx-summariser-work/fetch_metadata.json', 'r', encoding='utf-8') as f:
    meta = json.load(f)
print(meta['total_records'])
print(meta['total_chunks'])
print('yes' if meta.get('complete') else 'no')
PY
```

Assign stdout line 1 to `TOTAL_RECORDS`, line 2 to `TOTAL_CHUNKS`, and line 3 to `COMPLETE`.

If `COMPLETE` is not `yes`, STOP and report that Lenx MCP data fetching did not complete.

**4C — Verify chunk files exist:**

```bash
ls .lenx-summariser-work/chunk*.toon | wc -l
```

Chunk count varies because chunks are dynamically sized (~100 KB each). New data is constantly inserted into tasks, so `total` from the API is approximate. As long as `COMPLETE` is `yes`, all available data has been fetched.

**If `TOTAL_RECORDS` is `0`:** Tell the user "No data found for task TASK_ID in the specified time range" and STOP.

**If `TOTAL_CHUNKS` is `1`:** Set `SKIP_MERGE=true`. There is only one chunk so the recursive merge is unnecessary.

Proceed to Step 5.

## Step 5 — Summarise chunks (Level 0)

**YOU — the main agent — MUST execute this step yourself. Do NOT delegate Step 5 to a single subagent. YOU are the orchestrator. YOU call the Task tool directly, multiple times, to dispatch parallel subagents — one subagent per chunk.**

**MANDATORY: You MUST use the Task tool here. Reading chunk files yourself is FORBIDDEN — it will overflow your context with thousands of records and you will fail. If you do not use the Task tool you are doing this wrong.**

Do NOT think about what is in the chunks. Do NOT try to read them. Do NOT try to summarise them yourself. Do NOT wrap this step in a single Task call. Just dispatch subagents mechanically as described below.

### 5A — Calculate batches

```python
# You have TOTAL_CHUNKS chunks (0 to TOTAL_CHUNKS-1) and PARALLEL_CAP.
# Split into batches:
batches = []
for i in range(0, TOTAL_CHUNKS, PARALLEL_CAP):
    batches.append(list(range(i, min(i + PARALLEL_CAP, TOTAL_CHUNKS))))
```

Example: `TOTAL_CHUNKS=12`, `PARALLEL_CAP=5` → `[[0,1,2,3,4], [5,6,7,8,9], [10,11]]` → 3 batches.

### 5B — Dispatch one batch

**Call the Task tool multiple times IN THE SAME RESPONSE — one Task call per chunk index in the current batch.** This is the only way they run in parallel. If you make one Task call, wait, then make another, you are doing it sequentially and defeating the purpose.

For each chunk index `N` in the current batch, create one Task call. Copy this prompt EXACTLY — only replace `{N}`, `{TASK_ID}`, and `{USER_FOCUS}`:

```
Read the file .lenx-summariser-work/chunk{N}.toon — it contains Lenx monitoring data for task {TASK_ID} in TOON format (tab-delimited rows, header lines start with #).

User's analysis focus: "{USER_FOCUS}"

Columns: post_timestamp, post_message, thread_title, site, country, post_link, sentiment_score, medium, channel, reaction_count, comment_count, share_count, view_count, unix_timestamp (ignore last column).

Produce a 200-400 word summary covering:
- Key themes, topics, and patterns
- Sentiment breakdown (if relevant to focus)
- Notable data points, outliers, or trends
- Engagement highlights (reactions, comments, shares, views)
- Time distribution of records
- Relevant statistics (counts, percentages)
- 3-5 sample posts: include the FULL post_link URL and a one-line note on relevance

After the summary, add a section titled "## Key Identified Topics" with a bullet list of 5-10 distinct topics found in the data. Each bullet: a short topic label followed by a one-line description and approximate post count. Example:
- **Delivery delays** — Complaints about late or missed deliveries (approx. 34 posts)
- **Product quality** — Praise or concerns about build quality and materials (approx. 21 posts)

RULES: Do NOT mention "chunk", "batch", "TOON", or processing terminology. Write naturally. Do NOT read other files.

Write your summary to: .lenx-summariser-work/level0_summary_{N}.txt
```

Concrete example — if your current batch is `[0, 1, 2, 3, 4]`, you output exactly this in ONE assistant message:

```
Task("Summarise data 0", "<above prompt with N=0>")
Task("Summarise data 1", "<above prompt with N=1>")
Task("Summarise data 2", "<above prompt with N=2>")
Task("Summarise data 3", "<above prompt with N=3>")
Task("Summarise data 4", "<above prompt with N=4>")
```

All five in ONE message. Not five separate messages. Not one Task that handles all five.

### 5C — Wait

Do nothing until all Task calls from the current batch have returned.

### 5D — Next batch

Move to the next batch in the list from 5A. Go back to 5B. Repeat until every batch has been dispatched and returned.

### 5E — Verify

Run this command:

```bash
ls .lenx-summariser-work/level0_summary_*.txt | wc -l
```

This MUST equal `TOTAL_CHUNKS`. If any are missing, find which indices are missing and re-dispatch ONLY those using the same prompt from 5B. Then verify again.

**Do NOT proceed to Step 6 until all level0 summary files exist.**

## Step 6 — Recursive hierarchical merge

**YOU — the main agent — MUST execute this step yourself. Same rules as Step 5: YOU call the Task tool directly, YOU dispatch parallel subagents. Do NOT delegate the entire Step 6 to a single subagent.**

**If `SKIP_MERGE` is true:** Run this and skip to Step 7:

```bash
cp .lenx-summariser-work/level0_summary_0.txt .lenx-summariser-work/final_summary.txt
```

**Otherwise, execute this mechanical loop. Do NOT overthink it. Just follow 6A→6B→6C→6D mechanically.**

Set `LEVEL=1`. Then repeat:

### 6A — Group

Run this exact command (substitute LEVEL with the current number):

```bash
python3 "SKILL_DIR/scripts/merge-summaries.py" ".lenx-summariser-work" 5 LEVEL
```

Read the single line of output:
- `FINAL` → **STOP the loop.** `final_summary.txt` is ready. Go to Step 7.
- `0` → Error. STOP and report failure to user.
- A number → That is `NUM_GROUPS`. Continue to 6B.

### 6B — Dispatch merge subagents

Same rules as Step 5: **YOU call the Task tool, multiple times, IN THE SAME RESPONSE, batched by `PARALLEL_CAP`.** One Task call per group index.

For each group index `G` from `0` to `NUM_GROUPS - 1`, create one Task call. Copy this prompt EXACTLY — only replace `{LEVEL}`, `{G}`, `{TASK_ID}`, and `{USER_FOCUS}`:

```
Read the file .lenx-summariser-work/level{LEVEL}_group_{G}.txt — it contains multiple summaries of Lenx monitoring data for task {TASK_ID} that need to be merged.

User's analysis focus: "{USER_FOCUS}"

Merge into ONE coherent 300-500 word summary:
- Combine and deduplicate common themes
- Preserve important details, statistics, notable findings
- Identify cross-cutting patterns and trends
- Maintain quantitative data (counts, percentages, time ranges)
- Curate the best 3-5 sample posts with full post_link URLs

After the summary, add a section titled "## Key Identified Topics" with a consolidated bullet list of 5-10 distinct topics. Merge overlapping topics from the inputs, sum their approximate post counts, and keep only the most significant. Each bullet: a short topic label followed by a one-line description and approximate post count.

RULES: Do NOT mention "chunk", "batch", "merge", "level", "group", or processing terminology. Write seamlessly. Do NOT read other files.

Write merged summary to: .lenx-summariser-work/level{LEVEL}_summary_{G}.txt
```

All Task calls for this level in ONE message. Wait for all to return.

### 6C — Verify

Run this command (substitute LEVEL):

```bash
ls .lenx-summariser-work/level{LEVEL}_summary_*.txt | wc -l
```

Must equal `NUM_GROUPS`. Re-dispatch any missing ones.

### 6D — Next level

Set `LEVEL = LEVEL + 1`. Go back to 6A.

**Keep looping 6A→6B→6C→6D until 6A prints `FINAL`. Do NOT stop early. Do NOT skip levels. Do NOT quit because it feels like enough levels.**

Proceed to Step 7.

## Step 7 — Format output

Determine the output file name and extension:
- `FORMAT=text` → `lenx_task_{TASK_ID}_summary.txt`
- `FORMAT=markdown` → `lenx_task_{TASK_ID}_summary.md`
- `FORMAT=email` → `lenx_task_{TASK_ID}_summary.html`

Run this exact command:

```bash
python3 "SKILL_DIR/scripts/format-output.py" ".lenx-summariser-work/final_summary.txt" FORMAT "OUTPUT_FILE"
```

Verify the output file exists:

```bash
ls -la "OUTPUT_FILE"
```

Proceed to Step 8.

## Step 8 — Cleanup

Run this exact command:

```bash
rm -rf .lenx-summariser-work
```

After this, the ONLY file remaining from this entire process must be `OUTPUT_FILE`. Nothing else.

Verify cleanup:

```bash
ls .lenx-summariser-work 2>/dev/null && echo "ERROR: work dir still exists" || echo "cleanup OK"
```

Proceed to Step 9.

## Step 9 — Respond to user

Say exactly three things:

1. **File path:** "Report saved to: `{OUTPUT_FILE}`"
2. **Summary:** Read `OUTPUT_FILE` and provide a concise summary of its contents (key findings, overall sentiment, notable trends) — 3-6 sentences.
3. **Metadata:** "Task {TASK_ID} | {TIME_RANGE} | {TOTAL_RECORDS} records analysed"

Do NOT mention chunks, batches, levels, subagents, recursive merging, or any internal process. The user does not need to know how the report was produced.

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

---

## Reference — Output formats

| Format | Flag | Extension | Description |
|---|---|---|---|
| Text | `--text` | `.txt` | Plain text, no formatting |
| Markdown | `--markdown` | `.md` | Structured with headings, lists, sections |
| Email | `--email` | `.html` | Inline-styled HTML suitable for email clients |

Default is `markdown` if no flag is specified.

## Reference — Example walkthrough

User prompt:
```
/lenx-summarise all data for task 1528 in past 24 hours and focus on negative sentiment data --text
```

Exact agent execution:

| Step | Action | Result |
|---|---|---|
| 1 | Parse | `TASK_ID=1528`, `TIME_RANGE=past 24 hours`, `USER_FOCUS=negative sentiment data`, `FORMAT=text`, `PARALLEL_CAP=5`, `CHUNK_KB=100` |
| 2 | Check lenx-mcp stdio prerequisites | `lenx_get_task_data` MCP tool is available ✓ |
| 3 | Calculate timestamps | `FROM_TS=1745351234`, `TO_TS=1745437634` |
| 4 | Dispatch fetch subagent using `lenx_get_task_data` | `TOTAL_RECORDS=580`, `TOTAL_CHUNKS=4` (TOON format, ~100 KB/chunk, retries handled automatically) |
| 5 | Dispatch 4 subagents (1 batch of 4) | 4 × `level0_summary_*.txt` written |
| 6A | `merge-summaries.py ... 5 1` | `FINAL` (≤5 summaries → single merge) |
| 7 | `format-output.py ... text lenx_task_1528_summary.txt` | File created |
| 8 | `rm -rf .lenx-summariser-work` | Cleaned |
| 9 | Respond with file path + summary + metadata | Done |

## STRICT — Rules you MUST NOT break

1. Follow Steps 1–9 in exact order. Do not skip. Do not reorder. Do not add steps.
2. **YOU (the main agent) MUST be the one calling the Task tool in Steps 5 and 6.** Do NOT delegate Step 5 or Step 6 to a single subagent. YOU are the orchestrator. Subagents only do the actual summarisation work — one subagent per chunk or group file.
3. NEVER read chunk TOON files yourself. ALWAYS delegate to subagents via the Task tool.
4. NEVER dispatch more than `PARALLEL_CAP` Task calls at once. But ALWAYS dispatch up to `PARALLEL_CAP` — do not dispatch them one at a time.
5. ALL Task calls for one batch MUST be in the SAME assistant response. This is how parallelism works.
6. NEVER mention chunks, batches, levels, merging, or internal processing in any output — not in summaries, not in the final report, not in your response to the user.
7. ALWAYS include 3-5 sample posts with full `post_link` URLs in every summary at every level.
8. ALWAYS clean up `.lenx-summariser-work` before responding. The only artifact is `OUTPUT_FILE`.
9. ALWAYS use `MERGE_GROUP_SIZE=5`. Do not change this value. `CHUNK_KB` defaults to `100` but can be overridden by the user via `--chunk-kb N`.
10. ALWAYS pass `USER_FOCUS` to every subagent prompt so analysis stays targeted at all levels.
11. If a subagent fails or a file is missing, re-dispatch ONLY the failed subagent. Do not restart the entire process.
12. Do NOT stop early. Complete ALL batches in Step 5, ALL levels in Step 6, ALL steps through Step 9.
