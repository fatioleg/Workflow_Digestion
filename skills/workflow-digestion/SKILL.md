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

## Host portability (Claude Code / Codex / Antigravity)

This skill ships inside the `workflow-digestion` plugin. `scripts/run_pipeline.py` lives next to this `SKILL.md`; always resolve it relative to this skill's directory, never relative to the user's working directory.

- **Stage 1** needs only the `markitdown` CLI. If a `markitdown` skill is available, it may be used instead.
- **Stage 2** needs an LLM: the bare `graphify` CLI only extracts code, so on a document corpus it produces no `graph.json`. Use one of:
  1. **Agent route (default, all hosts):** invoke the `graphify` skill on `corpus/`. Install it per host with `graphify install --platform claude|codex|antigravity`. The host's own model does the semantic extraction.
  2. **Headless route:** `graphify extract ./corpus --backend claude|gemini|openai|...` with the matching API key set (e.g. `ANTHROPIC_API_KEY`). Writes `corpus/graphify-out/`.
  If neither is available, stop after Stage 1 and tell the user; do not run Stage 3 on a missing graph. The extraction rules for long papers below apply whenever the host can spawn subagents.
- **Stage 3** is deterministic Python and is identical on every host. After Stage 2, run `scripts/run_pipeline.py <source> --skip-markitdown --skip-graphify` with graphify's interpreter.

Prerequisites: `pip install 'markitdown[all]'` and `uv tool install graphifyy` (or `pip install graphifyy`).

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

Run graphify with `corpus/` as the working directory so outputs land in `<input>/corpus/graphify-out/`, which is where Stage 3 reads them.

### Long scientific papers: extraction rules (learned the hard way)

The graphify default of 20-25 files per subagent fails on long papers (300-5000 lines each). Subagents given ~6 full papers read only the abstracts and fill the rest from background knowledge. That violates graphify's "never invent an edge" rule. For paper corpora:

1. **Chunk by words, not by file count.** Use ~3 papers (~40k words) per subagent.
2. **Mandate full reading.** Add an addendum telling each subagent to Read every file to its last line in 400-line pieces. Forbid background-knowledge extraction, require `source_location` (section heading) on every node, and ask for "lines read / total lines" per file in the reply.
3. **Use global IDs for shared entities.** Models, datasets, benchmarks, metrics and software that recur across papers (AlphaFold3, PDBbind, PoseBusters, RDKit, AutoDock Vina...) get a stem-free ID (`alphafold3`, `pdbbind`) so they merge across chunks. Paper-specific concepts keep `{stem}_{entity}`. Without this, cross-paper links never form.
4. **Audit every chunk before merging.** Check nodes per source file (expect 25-50 per paper), distinct `source_location` values, and dangling endpoints. Send a shallow chunk back (SendMessage) rather than merging it.

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

Run `scripts/run_pipeline.py <input> --skip-markitdown --skip-graphify` with **graphify's own Python interpreter** (for example `%APPDATA%\uv\tools\graphifyy\Scripts\python.exe`), because Stage 3 imports `graphify.export`. It performs:

1. **Copy original documents first.** Copy top-level source files and every `corpus/*.md` into `obsidian-vault/_documentos_originais/`, named by basename with unsafe characters replaced by `_`. Never copy `corpus/`, `graphify-out/` or `obsidian-vault/` themselves. The old implementation did, so the vault copied itself into itself on every run.
2. **Scaffold with graphify** by calling `graphify.export.to_obsidian` + `to_canvas`. This writes node notes, `_COMMUNITY_*` notes and `graph.canvas`.
3. **Rewrite each node note in place**, keeping graphify's filename (`_dedup_node_filenames`). That keeps canvas cards and wikilinks resolving. Do NOT re-run `graphify export obsidian` afterwards, because it overwrites the enriched notes with stubs.
4. Use this template for each rewritten note:

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

   Links use graphify's note filenames (`[[<note filename>|<label>]]`), not raw node IDs. Excerpts are blockquoted, with `#` headings and code fences escaped so they cannot break the note's structure.

5. **Build index.md** with:
   - Statistics (nodes, edges, communities)
   - Most connected entities (top 10 by degree)
   - Community overview with 8 nodes per community
   - Links to key original documents

### Filename safety

Obsidian file/link rules: no `* " \ / < > : | ?` characters allowed, and `# ^ [ ]` break wikilinks. Replace all of these with `_` in both filenames and link paths. Use relative paths from the vault root (`_documentos_originais/...`), never absolute (`C:\...`).

Resolve `source_file` by **basename** (`Path(source_file).name`), never with `.replace("/", "__")`. On Windows the relative path uses backslashes, and the old string replace silently produced names that never matched the copied files, which left every "Conteúdo Relevante" section empty.

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

# Stage 3: Build enhanced Obsidian vault (graphify's interpreter; scaffolds + enriches in one pass)
"$APPDATA/uv/tools/graphifyy/Scripts/python.exe" scripts/run_pipeline.py <source> --skip-markitdown --skip-graphify
```

### Verify the vault

After Stage 3, check that every `[[link]]` target exists in the vault and that every `graph.canvas` file card points to an existing note. Also confirm `_documentos_originais/` holds no `obsidian-vault_*` or `corpus_*` copies.

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

- **Stage 1 fails:** install missing optional deps; report which file failed. Large PDFs need a long timeout (an 8 MB paper takes ~45 s).
- **Stage 2 fails:** re-run with `--force`; check graph health warnings
- **Stage 3 fails:** verify doc copies completed; verify community IDs are strings

## Cost and time estimates

- Reference run: 35 long papers (~450k words) took ~6 min of extraction with 9 parallel subagents, about 2.4M subagent tokens. The result was 1485 nodes, 3201 edges and 53 communities. Stage 3 took ~1 min.
- 50-100 files, mostly docs: ~5 min Stages 1+2, ~1 min Stage 3
- 500+ files: ~15 min Stages 1+2, ~3 min Stage 3
- LLM token cost is from Stage 2 semantic extraction; Stage 1+3 are deterministic

## What NOT to do

- Do not skip Stage 1 even if files are already `.md` — verify they are in `corpus/`, not the source folder
- Do not run Stage 3 with absolute paths in Obsidian links (causes "filename cannot contain..." errors)
- Do not over-extract: stay within chunk size guidance from the graphify skill
- Do not write content to the vault without first copying the original documents into `_documentos_originais/`