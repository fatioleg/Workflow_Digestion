---
name: workflow-digestion
description: Full pipeline that converts files to Markdown with markitdown, builds knowledge graphs with graphify, and creates an Obsidian vault with embedded document content and cross-entity connections.
license: MIT
metadata:
  author: fatioleg
  stack: markitdown -> graphify -> obsidian
---

# Workflow_Digestion

End-to-end pipeline that takes any folder of mixed-format files (PDF, DOCX, PPTX, XLSX, images) and produces a navigable Obsidian knowledge vault backed by an explicit knowledge graph.

## When to use

Use this skill when the user asks to:
- "Build a knowledge graph from these documents and link them in Obsidian"
- "Convert, extract, and link everything into a vault"
- "Apply markitdown, then graphify, then Obsidian"
- "Create a navigable vault from a folder of mixed files"

Do NOT use for: code-only repos (just graphify is enough), pure transcription (just markitdown), or quick single-document extraction.

## Pipeline overview

```
[Input folder] ─┬─> markitdown ──> .md files (corpus)
                └─> graphify    ──> graph.json, GRAPH_REPORT.md, graph.html
                                    └─> obsidian vault + doc copies + links
```

The pipeline runs three stages. Each stage depends on the previous one's output. If a stage fails, the user is told which stage and why, then prompted to continue or abort.

## Stage 1 - MarkItDown: convert source files to Markdown

MarkItDown converts PDFs, DOCX, PPTX, XLSX, images (OCR), audio, HTML, and other formats to clean Markdown. The output goes into `corpus/` next to the original files.

### Steps

1. **Detect source folder** from user input or default to `.`
2. **Create corpus directory** at `<input>/corpus/` (preserves relative layout)
3. **Convert each file** to Markdown, mirror structure:
   - `01_Schedule/day_01.jpg` → `corpus/01_Schedule/day_01.jpg.md`
   - `02_Reports/report.pdf` → `corpus/02_Reports/report.pdf.md`
4. **Use the markitdown skill** for the conversion. Skip files that already have a `.md` counterpart and `corpus/.md` is fresher than the source (idempotent reruns).

```bash
# Pseudo-flow:
for f in <input>/**/*.{pdf,docx,pptx,xlsx,jpg,png,html,csv,json,xml,zip,epub}; do
  out=<input>/corpus/<relative_path_with_.md>
  if [[ $f -nt $out ]] || [[ ! -f $out ]]; then
    markitdown "$f" > "$out"
  fi
done
```

### Office files note

MarkItDown requires optional deps for Office files. Install with `pip install 'markitdown[all]'` or `pip install 'markitdown[office]'`. PDFs need `pdfminer.six`. Images with OCR need `pytesseract`. Report any conversion failures explicitly to the user — do not silently skip.

### Stage 1 deliverable
- `<input>/corpus/` filled with `.md` files mirroring the source layout

---

## Stage 2 - Graphify: build knowledge graph from corpus

Graphify scans the corpus, extracts entities and relationships, clusters them, and produces:
- `graphify-out/graph.json` - NetworkX-compatible graph data
- `graphify-out/GRAPH_REPORT.md` - audit report with god nodes, surprising connections, suggested questions
- `graphify-out/graph.html` - interactive visualization
- `graphify-out/.graphify_labels.json` - community labels

### Steps

1. **Run detection**: scan corpus, classify files (code/document/paper/image), build `manifest.json` for incremental updates
2. **Check cache**: read `graphify-out/.graphify_root` for prior scan root
3. **Run structural extraction (AST)** for code files (deterministic, free)
4. **Run semantic extraction** in parallel for documents/papers/images using subagents
5. **Merge** AST + semantic into `.graphify_extract.json`
6. **Build graph**: cluster communities, score cohesion, identify god nodes and surprising connections
7. **Health check**: warn on dangling endpoints, missing endpoints, self-loops
8. **Label communities**: read node labels and write 2-5 word names per community
9. **Generate HTML** with auto-aggregation for graphs >5000 nodes
10. **Save manifest** + cost tracker

### Use the graphify skill for full detail

This pipeline delegates to the `graphify` skill — invoke it directly. The graphify skill has the exact subagent prompts, cluster configurations, and output formats. Do not duplicate that here.

### Stage 2 deliverable
- `graphify-out/graph.json` with nodes, links/edges, communities, hyperedges
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/graph.html`

---

## Stage 3 - Obsidian vault: navigable knowledge base

Build an Obsidian vault at `<input>/obsidian-vault/` with:
1. **One note per entity** from the graph
2. **Embedded content** from the original document (relevant section where the entity is mentioned)
3. **Bidirectional links** to other entities (`→` outgoing, `←` incoming)
4. **Copies of original documents** in `_documentos_originais/` so Obsidian links work without external paths
5. **Canvas file** (`graph.canvas`) for visual navigation
6. **Index** with community overview and key links

### Why this stage matters

graphify alone produces graph data, but Obsidian needs Markdown notes. The naive `graphify export obsidian` creates stub notes with metadata only — no actual document content. This stage fixes that by:

1. **Reading each original `.md`** from `_documentos_originais/`
2. **Extracting relevant sections** (where the entity is mentioned)
3. **Embedding that content** in the entity note
4. **Adding section anchors** so clicks navigate to the right place

### Steps

1. **Run `graphify export obsidian --dir <input>/obsidian-vault`** to scaffold the basic structure (notes + canvas)
2. **Copy original documents** into `obsidian-vault/_documentos_originais/` with safe filenames (replace `* " \ / < > : | ?` with `_`)
3. **Rebuild each note** with this template:

```markdown
---
type: graph-note
label: "<entity label>"
entity_type: <document|paper|concept|rationale>
community: "<community name or id>"
source_file: "_documentos_originais/<safe_filename>"
---

# <entity label>

📍 **Comunidade:** <community>

## 📄 Fonte Original

[[_documentos_originais/<safe_filename>|<original filename>]]

## 📖 Conteúdo Relevante Extraído

<first 50 lines around the entity mention in the source document, or first 50 lines if not found>

## 🔗 Conexões (N)

### → Conexões de saída
- → [[<target_id>|<target_label>]] — `<relation>`
- ...

### ← Conexões de entrada
- ← [[<source_id>|<source_label>]] — `<relation>`
- ...

## 📋 Metadados

| Campo | Valor |
|-------|-------|
| Tipo | <entity_type> |
| Comunidade | <community> |
| Conexões | N |
| Documento | [[_documentos_originais/<safe_filename>]] |
```

4. **Build index.md** with:
   - Statistics (nodes, edges, communities)
   - Most connected entities (top 10 by degree)
   - Community overview with 8 nodes per community
   - Links to key original documents

### Filename safety

Obsidian file/link rules: no `* " \ / < > : | ?` characters allowed. Replace with `_` in both filenames and link paths. Use relative paths from the vault root (`_documentos_originais/...`), never absolute (`C:\...`).

### Reading graph.json edges correctly

The graph.json file uses `links` (NetworkX format) for edges, not `edges`. Each link has:
- `source`: node id (source of edge)
- `target`: node id (target of edge)
- `relation`: e.g. `conceptually_related_to`, `references`, `cites`
- `confidence`: `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`

Some nodes have `community` as integer; cast to string when using in frontmatter.

### Stage 3 deliverable
- `<input>/obsidian-vault/` with 200+ notes, canvas, index, and document copies
- Each note has: embedded content, original doc link, bidirectional entity links

---

## Quick start commands

```bash
# Stage 1: Convert files to Markdown
python -m markitdown path/to/source > corpus/sources.md
# Or per-file conversion
markitdown "file.pdf" > "corpus/file.pdf.md"

# Stage 2: Build knowledge graph
graphify .                 # default run on current dir
graphify ./corpus --obsidian  # if corpus is separate

# Stage 3: Build enhanced Obsidian vault
graphify export obsidian --dir ./obsidian-vault
# Then run post-processing to embed content + copy docs (see scripts/run_pipeline.py)
```

## Decision: when to re-run which stage

- **Stage 1 only:** new office/PDF/image files added
- **Stages 2-3 only:** existing corpus changed (`.md` edited)
- **All stages:** new files of any type

Idempotency: each stage checks if its output is fresher than its input before running. Use a manifest (graphify's `manifest.json`) for Stage 2 incremental updates.

## Inputs the skill expects

- Path to source folder (defaults to `.`)
- Optional `--target` for vault location (defaults to `<source>/obsidian-vault`)
- Optional `--mode deep` for graphify (richer INFERRED edges)

## Outputs the skill produces

- `<source>/corpus/` — Markdown versions of all source files
- `<source>/graphify-out/` — graph.json, GRAPH_REPORT.md, graph.html
- `<source>/obsidian-vault/` — full navigable Obsidian vault with embedded content
- `<source>/obsidian-vault/_documentos_originais/` — copies of original docs for Obsidian links

## Failures and recovery

- **Stage 1 fails:** install missing optional deps; report which file failed
- **Stage 2 fails:** re-run with `--force`; check graph health warnings
- **Stage 3 fails:** verify doc copies completed; verify community IDs are strings

## Cost and time estimates

- 50-100 files, mostly docs: ~5 min Stages 1+2, ~1 min Stage 3
- 500+ files: ~15 min Stages 1+2, ~3 min Stage 3
- LLM token cost is from Stage 2 semantic extraction; Stage 1+3 are deterministic

## What NOT to do

- Do not skip Stage 1 even if files are already `.md` — verify they are in `corpus/`, not the source folder
- Do not run Stage 3 with absolute paths in Obsidian links (causes "filename cannot contain..." errors)
- Do not over-extract: stay within chunk size guidance from the graphify skill
- Do not write content to the vault without first copying the original documents into `_documentos_originais/`