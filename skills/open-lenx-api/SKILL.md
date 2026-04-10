---
name: open-lenx-api
description: "Fetch monitoring data from the Lenx Open API by task ID and date range. Use when the user asks to query Lenx tasks, pull Lenx data, integrate with the Lenx API, update task settings, or retrieve social monitoring posts."
---

# Lenx Open API

Lenx is a data monitoring system. This skill covers authenticating and calling the Lenx Open API to retrieve or update monitoring tasks.

## Credentials

Resolve each value using the **first available** source (in order):

| Value | Env Variable | Fallback |
|---|---|---|
| API Key | `LENX_API_KEY` | — (required; ask user) |
| User ID | `LENX_USER_ID` | — (required; ask user) |
| Endpoint | `LENX_ENDPOINT` | `https://open.lenx.ai` |

1. Use user-provided values first, then env variables.
2. If API Key or User ID cannot be resolved, **ask the user**.
3. Never hard-code or log credentials. Reference env variables (e.g., `$LENX_API_KEY`) in commands.

## Authentication

All requests require these headers:

| Header | Value |
|---|---|
| `x-api-key` | API key |
| `x-user-id` | User ID |

Two-tier auth: Tier 1 validates key+user, Tier 2 checks task-level access (valid credentials may still get 403).

---

## Endpoints

### Get Task Info

Retrieve metadata and search configuration for a specific task.

```
GET {endpoint}/api/v1/tasks/{task_id}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `task_id` | `number` | **Yes** | Path param — monitoring task ID |

#### Response (200 OK)

Cached 5 minutes. Returns `{ "data": { ... } }` with fields:

`task_id`, `task_name`, `owner_ac_id`, `task_type`, `indus_id`, `labels`, `lang_abbr`, `status`, `region`, `created_at`, `updated_at`, `search_query` (object or null with: `lang_abbr`, `region`, `list_medium`, `list_author_id`, `query_layer`, `query_string`, `cron`, `exclude_channel_links`, `updated_at`)

#### Errors

- **400** — Invalid request
- **401** — Invalid API key or user ID
- **403** — User does not have permission to access this task
- **404** — Task not found

---

### Get Task Data

```
GET {endpoint}/api/v1/tasks/{task_id}/data
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `task_id` | `number` | **Yes** | Path param — monitoring task ID |
| `from` | `number` | **Yes** | Start of date range (Unix timestamp, seconds) |
| `to` | `number` | **Yes** | End of date range (Unix timestamp, seconds) |
| `size` | `number` | **Yes** | Results to return (1–1000) |
| `search_after` | `number` | No | Pagination cursor — `unix_timestamp` of last result from previous page |

**Pagination:** Results are sorted by `unix_timestamp` descending. Pass the last item's `unix_timestamp` as `search_after` to get the next page. Repeat until fewer results than `size` are returned.

#### Response (200 OK)

Cached 5 minutes. Returns `{ "data": [...] }` where each item contains:

`id`, `hash`, `country`, `lang_abbr`, `medium`, `channel`, `channel_link`, `site`, `thread_link`, `post_link`, `thread_title`, `post_message`, `post_timestamp` (ISO 8601), `unix_timestamp`, `author_name`, `author_id`, `author_image`, `author_link`, `is_comment`, `comment_order`, `comment_count`, `share_count`, `view_count`, `reaction_count`, `reaction_like`, `reaction_dislike`, `reaction_love`, `reaction_wow`, `reaction_haha`, `reaction_sad`, `reaction_angry`, `sentiment_score`

#### Errors

- **400** — `{ "message": "Invalid request body", "error": "..." }`
- **401** — Invalid API key or user ID
- **403** — `{ "message": "Forbidden", "error": "User does not have permission to access this task" }`

### Update Task

```
PATCH {endpoint}/api/v1/tasks/{task_id}
```

**Body** (partial update — all fields optional):

- `task_name`: `string` (1–50 characters)
- `search_query`: `object` with optional fields:
  - `lang_abbr`: `string | null`
  - `region`: `string | null`
  - `list_medium`: `string[]`
  - `list_author_id`: `string[]`
  - `query_layer`: `EQLayer[] | null` — structured search logic (see below). Pass `null` to clear.
  - `exclude_channel_links`: `string[]`

> **Validation:** At least one of `task_name` or `search_query` must be provided. If `search_query` is provided, it must contain at least one field. Sending an empty body is invalid.

#### `query_layer` summary

`query_layer` is the user-friendly way to define search logic. When sent, the backend regenerates the internal `query_string` from it.

Each `EQLayer` has `in` (include terms) and `ex` (exclude terms). Quick rules:
- `string[]` → terms joined with `OR`
- `string[][]` → outer `AND`, inner `OR`
- Multiple layers are joined with `OR`
- `in` + `ex` in same layer → implicit `AND NOT`

> **When you need to build or modify `query_layer`:** Read the full reference at `QUERY_LAYER.md` (in this skill's directory) before constructing the payload. It contains type constraints, conversion logic, decision guides, examples, and common mistakes.

#### Response (200 OK)

```json
{ "data": { "task_id": 123, "updated": true } }
```

#### Errors

| Status | Condition |
|---|---|
| **400** | Invalid request body (validation failed, or `query_layer` could not be converted — `INVALID_QUERY_LAYER`) |
| **401** | Missing `x-user-id` header |
| **403** | User does not have permission to access this task |
| **404** | Task not found |
| **404** | Search query not found for this task |
| **500** | Unexpected error |

---

## Quick Examples

### curl — Get Data

```bash
curl -s "${LENX_ENDPOINT:-https://open.lenx.ai}/api/v1/tasks/42/data?from=1711929600&to=1714521600&size=10" \
  -H "x-api-key: $LENX_API_KEY" \
  -H "x-user-id: $LENX_USER_ID"
```

### curl — Update Task Name

```bash
curl -s -X PATCH "${LENX_ENDPOINT:-https://open.lenx.ai}/api/v1/tasks/42" \
  -H "x-api-key: $LENX_API_KEY" \
  -H "x-user-id: $LENX_USER_ID" \
  -H "Content-Type: application/json" \
  -d '{"task_name": "New Task Name"}'
```

### Pagination (Python)

```python
import os, requests

endpoint = os.getenv("LENX_ENDPOINT", "https://open.lenx.ai")
task_id = 42
all_posts, search_after = [], None

while True:
    params = {"from": 1711929600, "to": 1714521600, "size": 1000}
    if search_after is not None:
        params["search_after"] = search_after
    resp = requests.get(
        f"{endpoint}/api/v1/tasks/{task_id}/data",
        headers={"x-api-key": os.environ["LENX_API_KEY"], "x-user-id": os.environ["LENX_USER_ID"]},
        params=params,
    )
    resp.raise_for_status()
    page = resp.json()["data"]
    all_posts.extend(page)
    if len(page) < 1000:
        break
    search_after = page[-1]["unix_timestamp"]
```

---

## Workflow

1. **Resolve credentials** using the table above.
2. **Identify the task ID** — ask the user if not provided.
3. **Determine the operation** — fetching data or updating a task.
4. **For data retrieval:** Convert dates to Unix timestamps, set `size`, make GET request, paginate if needed.
5. **For task updates:** Build the PATCH body with only the fields being changed. If updating `query_layer`, read `QUERY_LAYER.md` first.
6. **Handle errors:** Surface validation (400), auth (401), and permission (403) errors clearly.
7. **Present results:** Summarize post count, date range, and key content.
