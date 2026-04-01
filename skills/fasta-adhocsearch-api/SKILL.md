---
name: fasta-adhocsearch-api
description: "Call the FASTA AdHocSearch API to search social media posts by query, keywords, date range, and country. Use when the user asks to search posts, query the adhocsearch API, or fetch data from the FASTA search service."
---

# Calling the AdHocSearch API

This skill guides agents through authenticating and calling the FASTA AdHocSearch REST API.

## Credentials & Configuration

Three values are required. Resolve each using the **first available** source (in order):

| Value | Env Variable | Settings / Config Key | Fallback |
|---|---|---|---|
| API Key | `ADHOCSEARCH_API_KEY` | User-provided or project config | — (required) |
| User ID | `ADHOCSEARCH_USER_ID` | User-provided or project config | — (required) |
| Endpoint URL | `ADHOCSEARCH_ENDPOINT` | User-provided or project config | `https://adhocsearch.fasta.ai` |

**Resolution rules:**
1. If the user explicitly provides a value (in chat, a config file, or `.env`), use it.
2. Otherwise check environment variables listed above.
3. For endpoint URL only, fall back to `https://adhocsearch.fasta.ai` if nothing is set.
4. If API Key or User ID cannot be resolved, **ask the user** before proceeding.

Never hard-code or log credentials. When constructing commands, prefer referencing environment variables (e.g., `$ADHOCSEARCH_API_KEY`) over inlining secrets.

## API Reference

### Endpoint

```
POST {endpoint}/search
```

### Required Headers

| Header | Value |
|---|---|
| `x-api-key` | The API key |
| `x-user-id` | The user ID |
| `Content-Type` | `application/json` |

### Request Body (JSON)

| Field | Type | Required | Description |
|---|---|---|---|
| `from` | `number` | **Yes** | Start of date range (Unix timestamp, seconds) |
| `to` | `number` | **Yes** | End of date range (Unix timestamp, seconds) |
| `size` | `number` | **Yes** | Number of results to return (1–1000) |
| `query` | `string` | No | Phrase search (max 50 chars). **Mutually exclusive with `keywords`.** |
| `keywords` | `string[]` | No | Keyword search, any-match (max 20 items, each max 50 chars). **Mutually exclusive with `query`.** |
| `search_after` | `number` | No | Cursor for pagination — the `unix_timestamp` of the last result from the previous page |
| `country` | `string` | No | Filter by country code |

> **Validation rules:**
> - `from`, `to`, and `size` must be positive numbers.
> - `size` must be ≤ 1000.
> - Only one of `query` or `keywords` may be provided, not both.

### Response

**200 OK**
```json
{
  "data": [
    {
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
      "reaction_angry": "number | null"
    }
  ]
}
```

**400 Bad Request** — invalid or missing body fields (Zod validation error).
**403 Forbidden** — user has no access record.
**500 Internal Server Error** — unexpected failure.

### Pagination

Results are sorted by `unix_timestamp` descending. To paginate:
1. Take the `unix_timestamp` of the **last** item in the current page.
2. Pass it as `search_after` in the next request (keep all other parameters the same).
3. Repeat until fewer results than `size` are returned.

## Usage Examples

### curl

```bash
curl -X POST "${ADHOCSEARCH_ENDPOINT:-https://adhocsearch.fasta.ai}/search" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ADHOCSEARCH_API_KEY" \
  -H "x-user-id: $ADHOCSEARCH_USER_ID" \
  -d '{
    "query": "climate change",
    "from": 1711929600,
    "to": 1714521600,
    "size": 10
  }'
```

### Python (requests)

```python
import os, requests

endpoint = os.getenv("ADHOCSEARCH_ENDPOINT", "https://adhocsearch.fasta.ai")
resp = requests.post(
    f"{endpoint}/search",
    headers={
        "Content-Type": "application/json",
        "x-api-key": os.environ["ADHOCSEARCH_API_KEY"],
        "x-user-id": os.environ["ADHOCSEARCH_USER_ID"],
    },
    json={
        "keywords": ["election", "vote"],
        "from": 1711929600,
        "to": 1714521600,
        "size": 50,
    },
)
data = resp.json()["data"]
```

### TypeScript / Node.js (fetch)

```typescript
const endpoint = process.env.ADHOCSEARCH_ENDPOINT ?? "https://adhocsearch.fasta.ai";
const res = await fetch(`${endpoint}/search`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.ADHOCSEARCH_API_KEY!,
    "x-user-id": process.env.ADHOCSEARCH_USER_ID!,
  },
  body: JSON.stringify({
    query: "artificial intelligence",
    from: 1711929600,
    to: 1714521600,
    size: 25,
  }),
});
const { data } = await res.json();
```

## Workflow

1. **Resolve credentials** using the resolution rules above.
2. **Build the request body** from the user's intent — convert human-readable dates to Unix timestamps, choose `query` vs `keywords` based on whether the user wants exact phrase or any-match.
3. **Make the POST request** to `{endpoint}/search`.
4. **Handle errors**: check status code, surface validation errors from 400 responses.
5. **Present results** clearly — summarize post count, date range covered, key content.
6. **Paginate** if the user wants more results than a single page.
