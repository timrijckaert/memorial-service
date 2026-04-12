# Key Decisions

Architectural choices and their rationale, distilled from design specs.

## UUID-Based Card Identity

Cards are identified by UUID4, not by filename. Filenames change when extracted data is corrected (because the derived filename includes name and death date). UUIDs are assigned at match confirmation and never change.

*See: 2026-04-08-stable-card-id-design.md*

## Fuzzy Filename Matching

Front/back pairs are matched by normalized filename similarity (token overlap), not by visual or content analysis. The scanning workflow produces predictable naming patterns (`Name.jpeg` / `Name 1.jpeg`), making fuzzy matching good enough and far simpler.

*See: 2026-04-07-fuzzy-matching-pipeline-design.md*

## No Frameworks

The project uses stdlib `http.server` and vanilla JavaScript. It's a personal tool for ~200 cards, running localhost-only. Build tools, bundlers, and frameworks would add complexity without proportional benefit.

*See: 2026-04-07-web-control-panel-design.md*

## Parallel OCR, Sequential LLM

OCR is CPU-bound and independent per image — it runs in parallel via asyncio. LLM calls are sequential because they share API rate limits and benefit from ordered processing for status reporting.

*See: 2026-04-07-async-pipeline-design.md*

## Export-Only Stitching

Image stitching (combining front+back into a single image) happens only during export, not during matching. Match-phase stitching was originally implemented but removed as redundant — the match UI shows images side-by-side without needing a stitched file.

*See: 2026-04-12-bugfixes-and-improvements-design.md, Task 7*

## Scraper: Image URL as File Key

Scraped JSON files are named after the image URL filename (e.g. `Scheerlinck-Maria-Celina-Haaltert-bidprentje-03-mei-1929.json`) rather than a name-based slug. Image URLs are naturally unique because they encode name, place, and death date. This avoids the need for deduplication logic when multiple people share the same name. Falls back to a name-based slug only for broken image links (2 out of 1567 entries).

*See: 2026-04-12-heemkring-scraper-design.md*

## State Persistence via JSON Restore

Match state (confirmed pairs, singles, unmatched images) is rebuilt on restart by scanning `output/json/` files and cross-referencing with `input/` images. No separate state file — the JSON output files *are* the persistent state.

*See: 2026-04-12-bugfixes-and-improvements-design.md, Task 6*
