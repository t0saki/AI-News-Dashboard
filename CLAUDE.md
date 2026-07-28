# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered news aggregation pipeline that filters RSS feeds through a two-stage LLM pipeline (L1 fast filter + L2 deep scorer), deduplicates stories, generates Chinese technical summaries, and ranks results using a gravity-based decay algorithm. Outputs `dashboard.json` and `top5.json`.

## Commands

```bash
# Run locally
uv run main.py

# Run tests (no test framework; plain scripts)
uv run python tests_response_utils.py
uv run python tests_schema_compat.py
uv run python tests_binary_split.py
uv run python tests_feed_timeout.py

# Install/sync dependencies
uv sync

# Docker
docker build -t news-dashboard .
docker run --env-file .env -v $(pwd)/data:/app/data news-dashboard
```

## Architecture

The main loop in `main.py` runs on a configurable interval (`FETCH_INTERVAL_SECONDS`):

1. **Fetch** — `sources/manager.py` iterates RSS feeds via `sources/rss.py`, inserts new items into SQLite with status `pending`. Feeds are downloaded by hand (urllib + per-socket timeout + total wall-clock budget) rather than by `feedparser.parse(url)`, which has no timeout at all.

A watchdog thread (`main.py`) arms on each cycle and disarms while sleeping; if a cycle exceeds `CYCLE_TIMEOUT_SECONDS` the process exits so the container restart policy recovers it.
2. **L1 Filter** — `processors/l1_filter.py` batches pending items, sends to a fast LLM (e.g. gpt-4o-mini) with prompts from `prompts/user_profile.md` + `prompts/l1_rules.md`. Items scoring ≥70 get status `l1_done`; others become `filtered`.
3. **L2 Scorer** — `processors/l2_scorer.py` takes `l1_done` items plus the current top-20 ranked items (for dedup context), sends to a stronger LLM with `prompts/l2_rules.md`. Produces Chinese title, summary, score, category. Status becomes `processed`. Duplicate stories are merged.
4. **Ranking** — `ranking.py` computes gravity scores: `score × (offset / (age_hours + offset))^effective_gravity` with score-adaptive decay (high scores decay slower). Results written to `data/dashboard.json` and `data/top5.json`.

### Key data flow statuses in SQLite (`news.status`)
`pending` → `l1_done` / `filtered` → `processed`

### AI interaction
`ai_service.py` wraps the OpenAI-compatible client with retry logic. `response_utils.py` handles robust JSON extraction from LLM output (fence stripping, thinking-tag removal, smart-quote normalization, fuzzy title matching for ID reconciliation).

## Configuration

All config via environment variables (see `.env_example`). `config.py` (`AppConfig`) reads them at import time. Key vars: `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL_L1`, `AI_MODEL_L2`, `FETCH_INTERVAL_SECONDS`, `GRAVITY`, `RANKING_WINDOW_HOURS`, `L1_BATCH_SIZE`, `L2_BATCH_SIZE`.

## Prompt Customization

`prompts/user_profile.md` defines the persona and interest tiers (Tier 1/2/3 scoring criteria). Mount or edit this file to change filtering behavior. `prompts/l1_rules.md` and `prompts/l2_rules.md` define the output JSON schemas and processing instructions for each stage.
