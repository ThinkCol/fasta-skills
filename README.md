# fasta.ai Agent Skills

Agent skills for FASTA and Lenx API workflows.

## Installation

```bash
# Install all skills
npx skills add ThinkCol/fasta-skills

# Install a specific skill
npx skills add ThinkCol/fasta-skills --skill fasta-adhocsearch-api
```

By default skills install to the current project. Add `-g` for a global install. Target a specific agent with `--agent` (e.g., `--agent amp`, `--agent cursor`).

## Available Skills

 | Skill | Description |
 |---|---|
 | [`fasta-adhocsearch-api`](skills/fasta-adhocsearch-api/SKILL.md) | Call the FASTA AdHocSearch API to search social media posts by query, keywords, date range, and country. |
 | [`open-lenx-cli`](skills/open-lenx-cli/SKILL.md) | Manage Lenx monitoring tasks via the `lenx` CLI. Requires `lenx` binary installed. |
 | [`lenx-task-summariser`](skills/lenx-task-summariser/SKILL.md) | Summarise Lenx task data via the configured `lenx-mcp` stdio MCP tool using recursive hierarchical summarisation. Handles large datasets (10,000+ records) via chunked parallel processing. |
 | [`lenx-wordcloud`](skills/lenx-wordcloud/SKILL.md)     | Generate wordcloud visualisations from Lenx task data via the lenx-mcp stdio server. Supports Chinese (jieba) and English tokenization, keyword filtering, and sentiment filtering. Requires Python 3 with wordcloud, matplotlib, Pillow, jieba. |
 | [`lenx-spike-detector`](skills/lenx-spike-detector/SKILL.md) | Detect activity spikes (volume, sentiment, engagement, topic) in Lenx task data via the lenx-mcp stdio server. Uses robust statistical detection (MAD-based) over adaptive time buckets. Requires Python 3; matplotlib for charts. |

## Contributing

Each skill follows the [Agent Skills open standard](https://github.com/anthropics/skills):

- Create a directory under `skills/` with the skill name
- Add a `SKILL.md` file with YAML frontmatter (`name`, `description`)
- Include usage examples in curl, Python, and TypeScript
