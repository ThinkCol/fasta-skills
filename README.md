# fasta.ai Agent Skills

Agent skills for FASTA and Lenx API workflows.

## Installation

```bash
# Install all skills
npx skills add fasta-ai/fasta-skills

# Install a specific skill
npx skills add fasta-ai/fasta-skills --skill fasta-adhocsearch-api
npx skills add fasta-ai/fasta-skills --skill open-lenx-api
```

By default skills install to the current project. Add `-g` for a global install. Target a specific agent with `--agent` (e.g., `--agent amp`, `--agent cursor`).

## Available Skills

| Skill | Description |
|---|---|
| [`fasta-adhocsearch-api`](skills/fasta-adhocsearch-api/SKILL.md) | Call the FASTA AdHocSearch API to search social media posts by query, keywords, date range, and country. |
| [`open-lenx-api`](skills/open-lenx-api/SKILL.md) | Fetch monitoring data from the Lenx Open API by task ID and date range. Retrieve social monitoring posts. |

## Contributing

Each skill follows the [Agent Skills open standard](https://github.com/anthropics/skills):

- Create a directory under `skills/` with the skill name
- Add a `SKILL.md` file with YAML frontmatter (`name`, `description`)
- Include usage examples in curl, Python, and TypeScript
