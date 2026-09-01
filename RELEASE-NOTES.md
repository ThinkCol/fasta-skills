## v1.0.0 (2026-09-01)

### Initial plugin release

- Skills now installable via native plugin/package managers: Claude Code (plugin marketplace), Claude Desktop (personal marketplace from GitHub), Codex (plugin marketplace), OpenCode (git plugin with optional `#vX.Y.Z` pin), Pi (`pi install git:...[@vX.Y.Z]`).
- Versioning: `scripts/bump-version.sh` syncs the version across all versioned manifests from package.json; `--check` detects drift.
- CI: release workflow validates manifests and creates a GitHub Release on `v*` tags.
