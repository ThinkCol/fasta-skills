# AGENTS.md — fasta-skills

## Project Overview
Agent skills repository for fasta.ai. Contains reusable SKILL.md files that guide AI coding agents through specific workflows (e.g., calling FASTA APIs). No build system, tests, or application code — this is a documentation-only repo.

## Structure
- `skills/<skill-name>/SKILL.md` — Each skill is a single Markdown file with YAML frontmatter (`name`, `description`) followed by instructions, API references, and usage examples.
- `README.md` — Repo-level description.

## Adding / Editing Skills
- Place each skill in its own directory under `skills/` with a `SKILL.md` file.
- Frontmatter is required: `name` (kebab-case, matching directory name) and `description` (quoted, includes trigger phrases for agent matching).
- Update the skills table in `README.md` when adding or removing a skill.
- Never hard-code or log credentials; reference env vars (e.g., `$ADHOCSEARCH_API_KEY`).
- Include usage examples in curl, Python, and TypeScript where applicable.

## Code Style
- Markdown: ATX headings (`#`), fenced code blocks with language tags, pipe tables with header separators.
- YAML frontmatter: quoted `description` values, unquoted `name`.
- Keep lines readable; no hard wrap limit enforced.

## Commands
No build, lint, or test commands — this repo contains only Markdown skill definitions.
