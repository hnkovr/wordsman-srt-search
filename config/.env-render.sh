#!/usr/bin/env bash
# Render a flat .env at the repo root from config/*.template files,
# expanding ${VAR:-default} against the current environment.
set -euo pipefail

cd "$(dirname "$0")/.."
out=.env
: >"$out"

for tpl in config/.env.config.template; do
  while IFS= read -r line; do
    case "$line" in
    '' | '#'*)
      printf '%s\n' "$line" >>"$out"
      continue
      ;;
    esac
    key=${line%%=*}
    val=${line#*=}
    rendered=$(eval "printf '%s' \"${val}\"")
    printf '%s=%s\n' "$key" "$rendered" >>"$out"
  done <"$tpl"
done

echo "rendered $out from config templates"
