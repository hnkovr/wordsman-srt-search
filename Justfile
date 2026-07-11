set shell := ["bash", "-euo", "pipefail", "-c"]

# List recipes
default:
    @just --list

# List registered providers and their status
providers:
    uv run srt-search providers

# Search subtitle candidates for a movie (JSON)
find movie year="" providers="":
    uv run srt-search find "{{ movie }}" {{ if year != "" { "--year " + year } else { "" } }} {{ if providers != "" { "--providers " + providers } else { "" } }}

# Download the best English SRT for a movie (prints saved path)
get movie year="" out="":
    uv run srt-search get "{{ movie }}" {{ if year != "" { "--year " + year } else { "" } }} {{ if out != "" { "--out " + out } else { "" } }}

# Live probe against real provider endpoints (network!) — not run in CI
probe-live movie="Dune" year="2021":
    uv run srt-search find "{{ movie }}" --year {{ year }} --providers podnapisi --limit 3

# Render flat .env from config templates
env-render:
    bash config/.env-render.sh
