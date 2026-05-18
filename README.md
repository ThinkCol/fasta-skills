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
 | [`lenx-task-summariser`](skills/lenx-task-summariser/SKILL.md) | Summarise Lenx task data from the `lenx-mcp` stdio server using recursive hierarchical summarisation. Handles large datasets (10,000+ records) via chunked parallel processing. |

## Contributing

Each skill follows the [Agent Skills open standard](https://github.com/anthropics/skills):

- Create a directory under `skills/` with the skill name
- Add a `SKILL.md` file with YAML frontmatter (`name`, `description`)
- Include usage examples in curl, Python, and TypeScript
