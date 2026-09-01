#!/bin/sh
# Sync versions across the repository's JSON manifests.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CONFIG=$REPO_ROOT/.version-bump.json

usage() {
  printf 'Usage: bump-version.sh X.Y.Z | --check\n'
}

require_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    printf '%s\n' "error: jq is required; install it with your package manager (for example, apt install jq or brew install jq)." >&2
    exit 1
  fi
}

json_path() {
  field=$1
  jq -nr --arg field "$field" \
    '$field | split(".") | map(if test("^[0-9]+$") then tonumber else . end)'
}

read_json_field() {
  file=$1
  field=$2
  field_path=$(json_path "$field")
  jq -er --argjson path "$field_path" \
    'getpath($path) | if type == "string" then . else error("version is not a string") end' \
    "$file"
}

manifest_entries() {
  jq -r '.files[] | [.path, .field] | @tsv' "$CONFIG"
}

check_versions() {
  require_jq
  if [ ! -f "$CONFIG" ]; then
    printf 'error: .version-bump.json not found at %s\n' "$CONFIG" >&2
    exit 1
  fi
  if [ ! -f "$REPO_ROOT/package.json" ]; then
    printf 'error: package.json not found at %s\n' "$REPO_ROOT/package.json" >&2
    exit 1
  fi

  package_version=$(read_json_field "$REPO_ROOT/package.json" version) || {
    printf '%s\n' 'error: could not read package.json version' >&2
    exit 1
  }
  entries=$(manifest_entries) || {
    printf '%s\n' 'error: could not read .version-bump.json files' >&2
    exit 1
  }

  drift=0
  while IFS="$(printf '\t')" read -r path field; do
    [ -n "$path" ] || continue
    file=$REPO_ROOT/$path
    if [ ! -f "$file" ]; then
      printf '%s: DRIFT (missing)\n' "$path"
      drift=1
      continue
    fi
    if current_version=$(read_json_field "$file" "$field" 2>/dev/null); then
      if [ "$current_version" = "$package_version" ]; then
        printf '%s: OK (%s)\n' "$path" "$current_version"
      else
        printf '%s: DRIFT (%s; package.json=%s)\n' "$path" "$current_version" "$package_version"
        drift=1
      fi
    else
      printf '%s: DRIFT (unreadable version)\n' "$path"
      drift=1
    fi
  done <<EOF
$entries
EOF

  return "$drift"
}

bump_version() {
  new_version=$1
  require_jq
  if ! printf '%s\n' "$new_version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    printf "error: '%s' is not a valid version; expected X.Y.Z\n" "$new_version" >&2
    exit 1
  fi
  if [ ! -f "$CONFIG" ]; then
    printf 'error: .version-bump.json not found at %s\n' "$CONFIG" >&2
    exit 1
  fi

  entries=$(manifest_entries) || {
    printf '%s\n' 'error: could not read .version-bump.json files' >&2
    exit 1
  }
  while IFS="$(printf '\t')" read -r path field; do
    [ -n "$path" ] || continue
    file=$REPO_ROOT/$path
    if [ ! -f "$file" ]; then
      printf 'error: manifest not found: %s\n' "$path" >&2
      exit 1
    fi
    old_version=$(read_json_field "$file" "$field") || {
      printf 'error: could not read %s (%s)\n' "$path" "$field" >&2
      exit 1
    }
    json_field=$(json_path "$field")
    tmp=$file.tmp.$$
    if ! jq --argjson path "$json_field" --arg version "$new_version" \
      'setpath($path; $version)' "$file" >"$tmp"; then
      rm -f "$tmp"
      printf 'error: could not update %s\n' "$path" >&2
      exit 1
    fi
    if ! mv "$tmp" "$file"; then
      rm -f "$tmp"
      printf 'error: could not replace %s\n' "$path" >&2
      exit 1
    fi
    printf '%s updated: %s -> %s\n' "$path" "$old_version" "$new_version"
  done <<EOF
$entries
EOF
}

case ${1-} in
--check)
  check_versions
  ;;
'')
  usage >&2
  exit 1
  ;;
--*)
  printf "error: unknown option '%s'\n" "$1" >&2
  usage >&2
  exit 1
  ;;
*)
  if [ "$#" -ne 1 ]; then
    usage >&2
    exit 1
  fi
  bump_version "$1"
  ;;
esac
