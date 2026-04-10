# `query_layer` Full Reference

This document contains the complete specification for building and updating `query_layer` objects in the Lenx Open API. Only load this file when you need to construct or modify a `query_layer`.

## Overview

`query_layer` is the structured JSON representation of search logic for a monitoring task. When sent via `PATCH /api/v1/tasks/{task_id}`, the backend regenerates the internal `query_string` (Elasticsearch syntax) from it.

- Prefer `query_layer` over hand-authoring `query_string`.
- Treat `query_string` as an implementation detail.
- Each `EQLayer` represents one searchable clause. Multiple `EQLayer` objects are joined with `OR`.

### Relationship to `query_string`

| Field | Role | Who should write it |
|---|---|---|
| `query_string` | Internal Elasticsearch query syntax | Backend only |
| `query_layer` | Structured JSON search logic | Users, agents, frontend |

If you send `query_layer`, `query_string` will be regenerated from it.

## Type Constraints

Each `EQLayer` may contain:

- `in`: terms to include
- `ex`: terms to exclude

For both `in` and `ex`, the accepted type is:

```ts
string[] | string[][]
```

This is a **strict union** — do **not** mix strings and nested arrays in the same field.

### Valid

```json
{ "in": ["a", "b"] }
{ "in": [["a", "b"], ["c"]] }
```

### Invalid

```json
{ "in": ["a", ["b"]] }
```

The conversion logic determines behavior from the first element (`x[0]`), so the array must be uniform.

## Conversion Logic

### Single field behavior

- `string[]` → `OR`
- `string[][]` → outer `AND`, inner `OR`
- `ex` values are wrapped as `NOT (...)`

| Input | Output logic |
|---|---|
| `{"in": ["a", "b"]}` | `(a) OR (b)` |
| `{"ex": ["a", "b"]}` | `NOT ((a) OR (b))` |
| `{"in": [["a", "b"], ["c"]]}` | `((a) OR (b)) AND ((c))` |
| `{"ex": [["a", "b"], ["c"]]}` | `NOT (((a) OR (b)) AND ((c)))` |

### Layer behavior

- Multiple `EQLayer` objects are joined with `OR`
- `in` and `ex` inside the same layer combine with implicit `AND`

| Structure | Output logic |
|---|---|
| `[{"in": ["a"]}, {"in": ["b"]}]` | `((a)) OR ((b))` |
| `[{"in": ["a"], "ex": ["b"]}]` | `((a)) AND NOT ((b))` |

## Decision Guide

| If the user says... | Use... |
|---|---|
| "A or B" | `"in": ["A", "B"]` |
| "A and B" | `"in": [["A"], ["B"]]` |
| "(A or B) and C" | `"in": [["A", "B"], ["C"]]` |
| "A but not B" | `"in": ["A"], "ex": ["B"]` |
| "strategy 1 or strategy 2" | two top-level `EQLayer` objects |

### Intent-to-shape mapping

| User intent | `query_layer` shape |
|---|---|
| Match **any** of several terms | `[{ "in": ["a", "b", "c"] }]` |
| Must include one from group A **and** one from group B | `[{ "in": [["a1", "a2"], ["b1", "b2"]] }]` |
| Match topic A **or** topic B | `[{ "in": ["topic-a"] }, { "in": ["topic-b"] }]` |
| Include terms but exclude noise | `[{ "in": ["a", "b"], "ex": ["noise"] }]` |
| Grouped includes and grouped excludes | `[{ "in": [["a", "b"], ["c"]], "ex": [["noise1", "noise2"], ["noise3"]] }]` |

## Examples

### 1. Simple OR

Find posts mentioning either Tesla or BYD.

```json
[{ "in": ["tesla", "byd"] }]
```

→ `(tesla) OR (byd)`

### 2. Grouped AND/OR

Find posts mentioning (EV or electric vehicle) AND (battery or charging).

```json
[{ "in": [["ev", "electric vehicle"], ["battery", "charging"]] }]
```

→ `((ev) OR (electric vehicle)) AND ((battery) OR (charging))`

### 3. Include with exclusions

Find Apple content but exclude fruit-related results.

```json
[{ "in": ["apple"], "ex": ["fruit", "recipe"] }]
```

→ `((apple)) AND NOT ((fruit) OR (recipe))`

### 4. Multiple top-level alternatives

Find either an EV topic or a solar topic.

```json
[
  { "in": [["ev", "electric vehicle"], ["battery"]] },
  { "in": [["solar", "photovoltaic"], ["panel"]] }
]
```

→ `(((ev) OR (electric vehicle)) AND ((battery))) OR (((solar) OR (photovoltaic)) AND ((panel)))`

### 5. Complex include and exclude groups

Find content about AI agents or copilots, require automation context, exclude job ads.

```json
[
  {
    "in": [["ai agent", "copilot"], ["automation", "workflow"]],
    "ex": [["job", "jobs", "hiring"]]
  }
]
```

→ `((ai agent) OR (copilot)) AND ((automation) OR (workflow)) AND NOT (((job) OR (jobs) OR (hiring)))`

## Common Mistakes

### 1. Mixing array shapes

❌ `{ "in": ["a", ["b"]] }` — choose flat `string[]` or nested `string[][]`, not both.

### 2. Using multiple layers when one grouped layer is needed

These are **not** equivalent:

- `[{ "in": ["a"] }, { "in": ["b"] }]` → `a OR b`
- `[{ "in": [["a"], ["b"]] }]` → `a AND b`

### 3. Forgetting that `ex` negates the whole field expression

`{ "ex": [["spam", "promo"], ["giveaway"]] }` means `NOT (((spam) OR (promo)) AND ((giveaway)))` — not separate independent exclusions.

### 4. Treating `query_string` and `query_layer` as separate sources of truth

They are linked. Updating `query_layer` regenerates `query_string`.

## PATCH Example with `query_layer`

```json
{
  "search_query": {
    "lang_abbr": ["en"],
    "list_medium": ["facebook", "news"],
    "query_layer": [
      {
        "in": [["tesla", "byd"], ["battery", "charging"]],
        "ex": ["stock", "share price"]
      }
    ],
    "exclude_channel_links": true
  }
}
```

**Before sending:**
- Validate array shape uniformity.
- Use nested arrays only when the user explicitly needs grouped `AND` logic.
- Inform user that changing `query_layer` regenerates `query_string`.
