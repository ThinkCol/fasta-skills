# fasta.ai Agent Skills

Agent skills for FASTA and Lenx API workflows.

## Installation

### Claude Code

```bash
claude plugin marketplace add ThinkCol/fasta-skills
claude plugin install fasta-skills@fasta-skills
```

In-session equivalent:

```text
/plugin marketplace add ThinkCol/fasta-skills
/plugin install fasta-skills@fasta-skills
```

Update:

```bash
claude plugin update fasta-skills
```

Updates arrive when the published version field bumps.

### Claude Desktop

In the Desktop app, go to Customize → Plugins → Personal plugins → `+` → Add marketplace from GitHub, enter `ThinkCol/fasta-skills`, then select Sync → Install.

Installs made via the terminal `claude` CLI appear only in Claude Code, not in Desktop chat. Use the in-app flow for Desktop.

### Codex (CLI and Codex app)

```bash
codex plugin marketplace add ThinkCol/fasta-skills
```

Then install via `/plugins` → search `fasta-skills` → Install Plugin. In the Codex app, use the Plugins sidebar.

### OpenCode

Add to `opencode.json` globally at `~/.config/opencode/opencode.json` or at the project level:

```json
{ "plugin": ["fasta-skills@git+https://github.com/ThinkCol/fasta-skills.git"] }
```

Pin a version by appending a ref:

```json
{ "plugin": ["fasta-skills@git+https://github.com/ThinkCol/fasta-skills.git#v1.0.0"] }
```

### Pi

```bash
pi install git:github.com/ThinkCol/fasta-skills
```

Pin:

```bash
pi install git:github.com/ThinkCol/fasta-skills@v1.0.0
```

Update:

```bash
pi update --extensions
```

Pinned installs stay put.

### Any other agent (npx skills)

```bash
npx skills add ThinkCol/fasta-skills          # all skills
npx skills add ThinkCol/fasta-skills --skill fasta-adhocsearch-api   # one skill
```

By default skills install to the current project. Add `-g` for a global install. Target a specific agent with `--agent` (e.g., `--agent amp`, `--agent cursor`).

## Versioning

The single repo-level semver is `1.0.0` in `package.json`. `scripts/bump-version.sh` syncs it to all plugin manifests, modeled on [obra/superpowers](https://github.com/obra/superpowers). Use `--check` to detect drift; CI enforces this check on release.

Releases are git tags in the form `vX.Y.Z` plus GitHub Releases. The changelog is maintained in [RELEASE-NOTES.md](RELEASE-NOTES.md).

- **Claude Code:** Update with `claude plugin update fasta-skills`; use the marketplace release version when pinning.
- **Claude Desktop:** Re-sync from the marketplace to update; pinning follows the marketplace’s published version.
- **Codex:** Reinstall from the marketplace to update; pinning follows the marketplace’s published version.
- **OpenCode:** Update the Git ref; pin by appending a tag such as `#v1.0.0`.
- **Pi:** Run `pi update --extensions`; pin by installing with a tag such as `@v1.0.0`.
- **npx skills:** Run `npx skills update`; pinning is not supported upstream, so installs always use the latest version.

| Agent | Update | Pin |
| --- | --- | --- |
| Claude Code | `claude plugin update fasta-skills` | Marketplace release version |
| Claude Desktop | Re-sync from the marketplace | Marketplace release version |
| Codex | Reinstall from the marketplace | Marketplace release version |
| OpenCode | Update the Git ref | Append `#v1.0.0` to the Git URL |
| Pi | `pi update --extensions` | Install with `@v1.0.0` |
| npx skills | `npx skills update` | Not supported upstream — always latest |

## Available Skills

 | Skill | Description |
 | --- | --- |
 | [`fasta-adhocsearch-api`](skills/fasta-adhocsearch-api/SKILL.md) | Call the FASTA AdHocSearch API to search social media posts by query, keywords, date range, and country. |
 | [`open-lenx-cli`](skills/open-lenx-cli/SKILL.md) | Manage Lenx monitoring tasks via the `lenx` CLI. Requires `lenx` binary installed. |
 | [`lenx-task-summariser`](skills/lenx-task-summariser/SKILL.md) | Summarise Lenx task data via the configured `lenx-mcp` stdio MCP tool using recursive hierarchical summarisation. Handles large datasets (10,000+ records) via chunked parallel processing. |
 | [`lenx-wordcloud`](skills/lenx-wordcloud/SKILL.md) | Generate wordcloud visualisations from Lenx task data via the lenx-mcp stdio server. Supports Chinese (jieba) and English tokenization, keyword filtering, and sentiment filtering. Requires Python 3 with wordcloud, matplotlib, Pillow, jieba. |
 | [`lenx-spike-detector`](skills/lenx-spike-detector/SKILL.md) | Detect activity spikes (volume, sentiment, engagement, topic) in Lenx task data via the lenx-mcp stdio server. Uses robust statistical detection (MAD-based) over adaptive time buckets. Requires Python 3; matplotlib for charts. |

## Contributing

Each skill follows the [Agent Skills open standard](https://github.com/anthropics/skills):

- Create a directory under `skills/` with the skill name
- Add a `SKILL.md` file with YAML frontmatter (`name`, `description`)
- Include usage examples in curl, Python, and TypeScript
