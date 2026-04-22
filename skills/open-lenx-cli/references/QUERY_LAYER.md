# `query_layer` Reference

For the full `query_layer` specification, see the canonical reference in the sibling [`open-lenx-api` skill](../../open-lenx-api/references/QUERY_LAYER.md), if it is installed.

This page provides a CLI-focused summary.

## Quick Usage with `lenx`

### Simple OR queries (`--search-text`)

```bash
lenx task create --name "Test" --language en --type live --search-text "tesla,byd"
```

### Complex queries (`--query`)

```bash
lenx task create --name "Test" --language en --type live \
  --query '[{"in":[["tesla","byd"],["battery"]],"ex":["stock"]}]'
```

## Quick Mapping

- `--search-text "a,b"` is best for simple OR matching.
- `--query '...'` is required for grouped AND/OR logic and exclusions.
- Prefer `query_layer` over hand-authoring low-level query strings.
