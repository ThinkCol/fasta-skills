---
name: open-lenx-api
description: "Fetch monitoring data from the Lenx Open API by task ID and date range. Use when the user asks to query Lenx tasks, pull Lenx data, integrate with the Lenx API, or retrieve social monitoring posts."
---

# Calling the Lenx Open API

This skill guides agents through authenticating and calling the Lenx Open API to retrieve task monitoring data.

## Overview

Lenx is a data monitoring system. The Lenx Open API allows users to fetch collected posts for a specific monitoring task within a date range. Each user is associated with an account that has access to specific tasks.

## Credentials & Configuration

Three values are required. Resolve each using the **first available** source (in order):

| Value | Env Variable | Settings / Config Key | Fallback |
|---|---|---|---|
| API Key | `LENX_API_KEY` | User-provided or project config | — (required) |
| User ID | `LENX_USER_ID` | User-provided or project config | — (required) |
| Endpoint URL | `LENX_ENDPOINT` | User-provided or project config | `https://open.lenx.ai` |

**Resolution rules:**
1. If the user explicitly provides a value (in chat, a config file, or `.env`), use it.
2. Otherwise check environment variables listed above.
3. For endpoint URL only, fall back to `https://open.lenx.ai` if nothing is set.
4. If API Key or User ID cannot be resolved, **ask the user** before proceeding.

Never hard-code or log credentials. When constructing commands, prefer referencing environment variables (e.g., `$LENX_API_KEY`) over inlining secrets.

## API Reference

### Get Task Data

Retrieve posts for a specific monitoring task within a date range.

```
GET {endpoint}/api/v1/tasks/{task_id}/data
```

### Required Headers

| Header | Value |
|---|---|
| `x-api-key` | The API key |
| `x-user-id` | The user ID |

### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `task_id` | `number` | **Yes** | The ID of the monitoring task to fetch data for |

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `from` | `number` | **Yes** | Start of date range (Unix timestamp, seconds). Must be positive. |
| `to` | `number` | **Yes** | End of date range (Unix timestamp, seconds). Must be positive. |
| `size` | `number` | **Yes** | Number of results to return (1–1000) |
| `search_after` | `number` | No | Cursor for pagination — the `unix_timestamp` of the last result from the previous page |

### Response

**200 OK** — cached for 5 minutes (`Cache-Control: public, max-age=300`)

```json
{
  "data": [
    {
      "id": "string",
      "hash": "string",
      "country": "string",
      "lang_abbr": "string",
      "medium": "string",
      "channel": "string",
      "channel_link": "string",
      "site": "string",
      "thread_link": "string",
      "post_link": "string",
      "thread_title": "string",
      "post_message": "string",
      "post_timestamp": "ISO 8601 datetime",
      "unix_timestamp": 1234567890,
      "author_name": "string",
      "author_id": "string | null",
      "author_image": "string | null",
      "author_link": "string | null",
      "is_comment": false,
      "comment_order": "number | null",
      "comment_count": "number | null",
      "share_count": "number | null",
      "view_count": "number | null",
      "reaction_count": "number | null",
      "reaction_like": "number | null",
      "reaction_dislike": "number | null",
      "reaction_love": "number | null",
      "reaction_wow": "number | null",
      "reaction_haha": "number | null",
      "reaction_sad": "number | null",
      "reaction_angry": "number | null",
      "sentiment_score": "number | null"
    }
  ]
}
```

**400 Bad Request** — invalid parameters

```json
{
  "message": "Invalid request body",
  "error": "validation error details"
}
```

**403 Forbidden** — user does not have access to the requested task

```json
{
  "message": "Forbidden",
  "error": "User does not have permission to access this task"
}
```

**401 Unauthorized** — invalid API key or user ID

### Authentication

The API uses a two-tier authorization model:
1. **Tier 1**: The `x-api-key` and `x-user-id` headers are validated to authenticate the user.
2. **Tier 2**: The server checks whether the authenticated user has permission to access the specific `task_id`.

A valid API key/user pair may still receive a 403 if they don't have access to the requested task.

### Pagination

Results are sorted by `unix_timestamp` descending (newest first). To paginate:
1. Take the `unix_timestamp` of the **last** item in the current page.
2. Pass it as `search_after` in the next request (keep all other parameters the same).
3. Repeat until fewer results than `size` are returned.

## Usage Examples

### curl

```bash
curl -s "${LENX_ENDPOINT:-https://open.lenx.ai}/api/v1/tasks/42/data?from=1711929600&to=1714521600&size=10" \
  -H "x-api-key: $LENX_API_KEY" \
  -H "x-user-id: $LENX_USER_ID"
```

### Python (requests)

```python
import os, requests

endpoint = os.getenv("LENX_ENDPOINT", "https://open.lenx.ai")
task_id = 42

resp = requests.get(
    f"{endpoint}/api/v1/tasks/{task_id}/data",
    headers={
        "x-api-key": os.environ["LENX_API_KEY"],
        "x-user-id": os.environ["LENX_USER_ID"],
    },
    params={
        "from": 1711929600,
        "to": 1714521600,
        "size": 100,
    },
)
resp.raise_for_status()
posts = resp.json()["data"]
```

### TypeScript / Node.js (fetch)

```typescript
const endpoint = process.env.LENX_ENDPOINT ?? "https://open.lenx.ai";
const taskId = 42;

const params = new URLSearchParams({
  from: "1711929600",
  to: "1714521600",
  size: "25",
});

const res = await fetch(
  `${endpoint}/api/v1/tasks/${taskId}/data?${params}`,
  {
    headers: {
      "x-api-key": process.env.LENX_API_KEY!,
      "x-user-id": process.env.LENX_USER_ID!,
    },
  }
);
const { data } = await res.json();
```

### Pagination Example (Python)

```python
import os, requests

endpoint = os.getenv("LENX_ENDPOINT", "https://open.lenx.ai")
task_id = 42
all_posts = []
search_after = None

while True:
    params = {"from": 1711929600, "to": 1714521600, "size": 1000}
    if search_after is not None:
        params["search_after"] = search_after

    resp = requests.get(
        f"{endpoint}/api/v1/tasks/{task_id}/data",
        headers={
            "x-api-key": os.environ["LENX_API_KEY"],
            "x-user-id": os.environ["LENX_USER_ID"],
        },
        params=params,
    )
    resp.raise_for_status()
    page = resp.json()["data"]
    all_posts.extend(page)

    if len(page) < 1000:
        break
    search_after = page[-1]["unix_timestamp"]
```

## Workflow

1. **Resolve credentials** using the resolution rules above.
2. **Identify the task ID** — the user must know which monitoring task they want data from.
3. **Build the request** — convert human-readable dates to Unix timestamps, set a reasonable `size`.
4. **Make the GET request** to `{endpoint}/api/v1/tasks/{task_id}/data` with query parameters.
5. **Handle errors**: check status code, surface validation errors from 400, permission errors from 403.
6. **Present results** clearly — summarize post count, date range covered, key content.
7. **Paginate** if the user wants more results than a single page (max 1000 per request).
