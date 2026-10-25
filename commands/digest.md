---
description: Run the Workflow_Digestion pipeline (markitdown -> graphify -> Obsidian) on a folder
argument-hint: "[source_folder] [--target <vault>] [--skip-markitdown] [--skip-graphify] [--skip-obsidian]"
---

Use the `workflow-digestion` skill to digest the folder given in `$ARGUMENTS` (default: the current directory).

1. Check prerequisites: `markitdown` and `graphify` on PATH, and graphify's own Python interpreter for Stage 3.
2. Run the stages in order, honouring any `--skip-*` flags in the arguments.
3. Report per-stage results (files converted/failed, nodes/edges/communities, notes written) and verify the vault (all wikilinks and canvas cards resolve; no `corpus_*`/`obsidian-vault_*` copies in `_documentos_originais/`).
