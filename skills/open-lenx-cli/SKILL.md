---
name: open-lenx-cli
description: Manage Lenx monitoring tasks via the `lenx` CLI. Use when you need to query Lenx tasks, pull Lenx monitoring data, create/update/delete tasks, or export data via the command line. Requires the `lenx` binary installed and `lenx init` configured. Invoke as: lenx <command> [flags].
---

# Lenx CLI (`lenx`)

A command-line client for the Lenx Open API.

## When to Use This Skill

- You have the `lenx` binary available.
- You want convenient command-line workflows instead of raw HTTP requests.
- You need to list tasks, inspect task details, create/update/delete tasks, or export task data.

## Binary Installation Check

Before using any `lenx` command, verify the binary exists:

```bash
which lenx 2>/dev/null || curl -fsSL https://raw.githubusercontent.com/ThinkCol/lenx-cli/main/install.sh | sh
```

If `lenx` is not found, run the install script above. The script detects OS/arch, downloads the latest release, and installs to `/usr/local/bin` (override with `LENX_INSTALL_DIR`).

## Relationship to `open-lenx-api`

- Use `open-lenx-cli` when the `lenx` binary is installed and you want the fastest interactive workflow.
- Use `open-lenx-api` when you need raw HTTP requests, programmatic integration, or the CLI is unavailable.

## Prerequisites

- Go 1.26+ if installing from source.
- `lenx` binary installed via:

```bash
curl -fsSL https://raw.githubusercontent.com/ThinkCol/lenx-cli/main/install.sh | sh
```

- Or build from source:

```bash
git clone https://github.com/fasta/lenxcli.git
cd lenxcli && make install
```

## Setup

```bash
lenx init
# Follow prompts, or:
lenx init --url https://open.lenx.ai --user-id YOUR_ID --token YOUR_TOKEN
```

## Commands

### `lenx task get <task-id>`

Retrieve task details.

### `lenx task data <task-id> --from TIMESTAMP --to TIMESTAMP --size N [--search-after TIMESTAMP]`

Retrieve monitoring data for a task. `--from` and `--to` are Unix timestamps in milliseconds. `--size` controls the number of results (1-1000). Use `--search-after` for pagination with the `unix_timestamp` of the last result from the previous page.

### `lenx task list [--page N] [--size N]`

List all accessible tasks.

### `lenx task create --name NAME --language LANG --type live --search-text TERMS`

Create a new monitoring task. Use `--query` for raw JSON `query_layer`.

### `lenx task update <task-id> [--name NAME] [--search-text TERMS] [--query JSON]`

Update task name or search query.

### `lenx task delete <task-id>`

Delete a monitoring task.

### `lenx task export --task-id ID --from TIMESTAMP --to TIMESTAMP --columns COLS --format xlsx --email EMAIL`

Export task data asynchronously. Result is emailed.

### `lenx update`

Self-update to the latest release from GitHub. No configuration required.

## Output

All commands output raw JSON to stdout. Errors go to stderr with exit code 1.

## Query Layer

For complex search queries, use `--query` with a raw JSON `query_layer`:

```bash
lenx task create --name "Test" --language en --type live \
  --query '[{"in":[["tesla","byd"],["battery"]],"ex":["stock"]}]'
```

For simple OR queries, use `--search-text`:

```bash
lenx task create --name "Test" --language en --type live --search-text "tesla,byd"
```

See [`references/QUERY_LAYER.md`](references/QUERY_LAYER.md) for the CLI-focused `query_layer` reference.

## Environment Variables

- `LENX_CONFIG` — override the config file path used by the CLI.

## Workflow

1. Run `lenx init` if not configured.
2. Use `lenx task list` to find task IDs.
3. Use `lenx task get <id>` for details, and `lenx task data <id>` to retrieve monitoring data.
4. Use `lenx task create/update/delete` to manage tasks.
5. Use `lenx task export` for async data export.
