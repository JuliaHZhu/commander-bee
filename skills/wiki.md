---
name: wiki
description: Operate the LLM Wiki — initialize, ingest sources, query knowledge, lint integrity. Karpathy-style interlinked markdown KB adapted for worker-bee.
trigger: wiki, knowledge base, 知识库, 笔记, ingest, query, lint, 整理笔记
tools:
  - fs_read_file
  - fs_write_file
  - fs_search_files
  - sys_terminal
  - net_web_search
  - net_web_extract
---

# LLM Wiki (Karpathy Pattern)

Build and maintain a persistent, compounding knowledge base as interlinked markdown files.
Unlike RAG (which rediscovers per query), the wiki compiles once and keeps current.

## When This Skill Activates

- User asks to create/start a wiki
- User provides a source to ingest (URL, file, paste)
- User asks a question and a wiki exists
- User asks to lint, audit, or health-check the wiki
- User references "notes", "knowledge base", or "wiki"

## Wiki Location

Path: `${WIKI_PATH:-$HOME/wiki-worker-bee}`

Worker-bee resolves this via env var or falls back to `~/wiki-worker-bee`.

## Architecture

```
wiki-worker-bee/
├── SCHEMA.md           # Domain conventions, tag taxonomy, thresholds
├── index.md            # Sectioned catalog with one-line summaries
├── log.md              # Chronological action log (append-only, rotate yearly)
├── raw/                # Layer 1: Immutable source material (open-ended)
│   # Create subdirs as needed: articles/, papers/, ideas/, news/, designs/, ...
├── entities/           # Layer 2: People, orgs, products, user profile
├── concepts/           # Layer 2: Topics, techniques, theories
├── comparisons/        # Layer 2: Side-by-side analyses
├── queries/            # Layer 2: Filed query results
└── _meta/              # Meta: SCHEMA.md, index.md, log.md
```

**Layer 1 — Raw:** Immutable. Agent reads but never modifies.
**Layer 2 — Wiki:** Agent-owned. Created, updated, cross-referenced by agent.
**Layer 3 — Schema:** `SCHEMA.md` defines structure, tags, update policy.

## Resuming an Existing Wiki (CRITICAL)

Every session that touches the wiki MUST orient first:

1. Read `SCHEMA.md`
2. Read `index.md`
3. Read last 20-30 lines of `log.md`

```bash
WIKI="${WIKI_PATH:-$HOME/wiki-worker-bee}"
# Use fs_read_file on these three files
```

Only then ingest, query, or lint.

## Core Operations

### 1. Initialize New Wiki

When user asks to create a wiki:

1. Determine path (env var or ask; default `~/wiki-worker-bee`)
2. Create directory structure above
3. Ask user for domain — be specific
4. Write `SCHEMA.md` (customized to domain)
5. Write `index.md`, `log.md`
6. Confirm ready; suggest first sources

### 2. Ingest

When user provides a source:

1. **Capture raw:** URL → `net_web_extract`, save to `raw/articles/`. PDF → `net_web_extract`, save to `raw/papers/`. Text → save to `raw/transcripts/`. Session data → save to `raw/sessions/`.
   - Name descriptively: `karpathy-llm-wiki-2026.md`
   - Add raw frontmatter:
     ```yaml
     ---
     source_url: https://...
     ingested: YYYY-MM-DD
     sha256: <hex digest of body>
     ---
     ```

2. **Discuss takeaways** with user (skip in automated contexts).

3. **Check existing pages** — search `index.md` and `fs_search_files` for duplicates.

4. **Write/update wiki pages:**
   - New pages only if meeting thresholds (2+ source mentions or central)
   - Existing pages: add info, bump `updated` date
   - Cross-reference: minimum 2 `[[wikilinks]]` per page
   - Tags: only from SCHEMA.md taxonomy
   - Provenance: append `^[raw/articles/source.md]` on paragraphs from specific sources
   - Confidence: `high|medium|low` in frontmatter for opinion-heavy claims

5. **Update navigation:**
   - Add to `index.md` under correct section
   - Update "Total pages" count and "Last updated"
   - Append to `log.md`

6. **Report changes** — list every file created/updated.

### 3. Query

When user asks about wiki domain:

1. Read `index.md` for relevant pages
2. For large wikis (100+ pages), also `fs_search_files`
3. Read relevant pages with `fs_read_file`
4. Synthesize answer, citing `[[page-name]]`
5. File valuable answers back to `queries/` or `comparisons/`
6. Update `log.md`

### 4. Lint

When user asks to audit:

1. Orphan pages (no inbound `[[wikilinks]]`)
2. Broken wikilinks (point to non-existent pages)
3. Index completeness (every wiki page in `index.md`)
4. Frontmatter validation (required fields, taxonomy compliance)
5. Stale content (`updated` >90 days older than latest source)
6. Contradictions (`contested: true`, `contradictions:`)
7. Quality signals (`confidence: low`, single-source unflagged)
8. Source drift (recompute `sha256` in `raw/`, flag mismatches)
9. Page size (flag >200 lines)
10. Tag audit (flag tags not in taxonomy)
11. Log rotation (if `log.md` >500 entries, rotate)
12. Report grouped by severity; append to `log.md`

## Frontmatter Templates

**Wiki page:**
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from taxonomy]
sources: [raw/articles/source.md]
confidence: high | medium | low
contested: true
contradictions: [other-page-slug]
---
```

**Raw source:**
```yaml
---
source_url: https://...
ingested: YYYY-MM-DD
sha256: <hex digest of body>
---
```

## Scaling Rules

- Section >50 entries → split by first letter or sub-domain
- Index >200 entries total → create `_meta/topic-map.md`
- Page >200 lines → split into sub-topics with cross-links
- `log.md` >500 entries → rotate to `log-YYYY.md`

## Pitfalls

- NEVER modify files in `raw/` — sources are immutable
- ALWAYS orient first (SCHEMA + index + log) before operating
- ALWAYS update `index.md` and `log.md` — skipping degrades the wiki
- Don't create pages for passing mentions — follow thresholds
- Don't create pages without cross-references — isolated pages are invisible
- Tags must come from taxonomy — freeform tags decay into noise
- Handle contradictions explicitly — don't silently overwrite
