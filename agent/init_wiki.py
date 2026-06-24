#!/usr/bin/env python3
"""Initialize LLM Wiki for worker-bee.

Usage:
    python init_wiki.py [WIKI_PATH]

Defaults to ~/wiki-worker-bee or $WIKI_PATH env var.
"""
import os
import sys
from pathlib import Path


def main():
    wiki_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WIKI_PATH", str(Path.home() / "wiki-worker-bee"))
    wiki = Path(wiki_path)

    if wiki.exists() and any(wiki.iterdir()):
        print(f"⚠️  Wiki already exists at {wiki}. Skipping initialization.")
        print("   To re-initialize, remove the directory first.")
        return

    # Create structure
    dirs = [
        wiki / "raw",
        wiki / "entities",
        wiki / "concepts",
        wiki / "comparisons",
        wiki / "queries",
        wiki / "_meta",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # SCHEMA.md
    schema = wiki / "SCHEMA.md"
    schema.write_text("""# Wiki Schema

## Domain
Worker-bee operations, skill design, and user-AI interaction notes.

## Conventions
- File names: lowercase, hyphens, no spaces
- Every wiki page starts with YAML frontmatter
- Use `[[wikilinks]]` to link between pages (minimum 2 outbound links per page)
- When updating a page, always bump the `updated` date
- Every new page must be added to `index.md` under the correct section
- Every action must be appended to `log.md`
- Provenance markers: append `^[raw/articles/source-file.md]` on paragraphs from specific sources

## Frontmatter
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary | objective-record | inference
tags: [from taxonomy below]
sources: [raw/articles/source-name.md]
confidence: high | medium | low
contested: true
contradictions: [other-page-slug]
---
```

## Tag Taxonomy
- **meta**: wiki, schema, log, index, lint
- **skill**: skill-design, skill-evolution, trigger, deck, registry
- **interaction**: user-expectation, mental-model, feedback-loop, halt
- **tool**: filesystem, web, terminal, subagent
- **domain**: code-review, web-research, system-design
- **user**: user-profile, preference, pattern

## Page Thresholds
- Create when entity/concept appears in 2+ sources OR is central to one
- Add to existing page when source mentions something already covered
- DON'T create for passing mentions or out-of-domain details
- Split when page exceeds ~200 lines
- Archive when fully superseded — move to `_archive/`, remove from index

## Entity Pages
One page per notable entity. Include: overview, key facts, relationships, sources.

## Concept Pages
One page per concept. Include: definition, current state, open questions, related concepts.

## Comparison Pages
Side-by-side. Include: what, dimensions (table), verdict, sources.

## Learn-From-Doing Pages
- **objective/**: Immutable factual record of a session. No speculation.
- **inference/**: Hypothesis about user expectation. Anchored to concrete cultural references.

## Update Policy
When new info conflicts:
1. Check dates — newer generally supersedes
2. If genuinely contradictory, note both positions with dates and sources
3. Mark contradiction in frontmatter
4. Flag for user review in lint report
""", encoding="utf-8")

    # index.md
    index = wiki / "index.md"
    index.write_text("""# Wiki Index

> Content catalog. Every wiki page listed under its type with a one-line summary.
> Read this first to find relevant pages for any query.
> Last updated: {date} | Total pages: 0

## Entities

## Concepts

## Comparisons

## Queries

## Learn-From-Doing

### Objective Records

### Inference Records
""".format(date=__import__('datetime').datetime.now().strftime("%Y-%m-%d")), encoding="utf-8")

    # log.md
    log = wiki / "log.md"
    log.write_text(f"""# Wiki Log

> Chronological record of all wiki actions. Append-only.
> Format: `## [YYYY-MM-DD] action | subject`
> Actions: ingest, update, query, lint, create, archive, delete

## [{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}] create | Wiki initialized
- Domain: worker-bee operations & learnings
- Structure created with SCHEMA.md, index.md, log.md
""", encoding="utf-8")

    print(f"✅ Wiki initialized at {wiki}")
    print(f"   Set WIKI_PATH={wiki} in your environment to use this wiki.")


if __name__ == "__main__":
    main()
