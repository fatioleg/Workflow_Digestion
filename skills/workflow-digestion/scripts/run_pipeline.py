#!/usr/bin/env python3
"""
Workflow_Digestion runner: executes the full markitdown -> graphify -> obsidian pipeline.

Usage:
    python run_pipeline.py [source_folder] [--target <vault_path>]

Stage 3 imports graphify, so run this script with graphify's own interpreter
(e.g. the uv tool venv: %APPDATA%\\uv\\tools\\graphifyy\\Scripts\\python.exe).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# Generated folders inside <source>; never treat them as source material.
GENERATED_DIRS = {"corpus", "graphify-out", "obsidian-vault"}

# Characters that break Obsidian filenames or wikilinks.
UNSAFE_CHARS = r'[*"\\/<>:|?#^\[\]]'


def is_generated(path: Path, source: Path) -> bool:
    return any(part in GENERATED_DIRS for part in path.relative_to(source).parts)


def run_stage1_markitdown(source: Path, corpus: Path) -> dict:
    """Stage 1: Convert source files to Markdown using markitdown."""
    print("\n=== Stage 1: MarkItDown Conversion ===\n")

    stats = {"converted": 0, "skipped": 0, "failed": 0}

    if not source.exists():
        print(f"ERROR: Source folder not found: {source}")
        return stats

    # Find all supported files
    extensions = {".pdf", ".docx", ".pptx", ".xlsx", ".jpg", ".jpeg", ".png",
                  ".gif", ".webp", ".wav", ".mp3", ".html", ".csv", ".json",
                  ".xml", ".epub", ".txt"}

    files = [f for f in source.rglob("*")
             if f.is_file() and f.suffix.lower() in extensions and not is_generated(f, source)]

    print(f"Found {len(files)} convertible files")

    # Convert each file
    for src in files:
        rel = src.relative_to(source)
        out = corpus / rel.parent / f"{src.name}.md"
        out.parent.mkdir(parents=True, exist_ok=True)

        # Skip if output is newer
        if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            stats["skipped"] += 1
            continue

        # Plain text needs no conversion
        if src.suffix.lower() == ".txt":
            shutil.copy2(src, out)
            stats["converted"] += 1
            print(f"  ✓ {rel}")
            continue

        try:
            cmd = ["markitdown", str(src), "-o", str(out)]
            # Large PDFs (e.g. 8 MB papers) take ~45 s; 60 s was too tight.
            result = subprocess.run(cmd, capture_output=True, timeout=600)

            if result.returncode == 0 and out.exists():
                stats["converted"] += 1
                print(f"  ✓ {rel}")
            else:
                stats["failed"] += 1
                print(f"  ✗ {rel}: {result.stderr.decode(errors='ignore')[:100]}")
        except subprocess.TimeoutExpired:
            stats["failed"] += 1
            print(f"  ✗ {rel}: timeout")
        except FileNotFoundError:
            # Try python -m markitdown
            try:
                cmd = [sys.executable, "-m", "markitdown", str(src)]
                result = subprocess.run(cmd, capture_output=True, timeout=600)
                if result.returncode == 0:
                    out.write_text(result.stdout.decode("utf-8", errors="ignore"), encoding="utf-8")
                    stats["converted"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                stats["failed"] += 1
                print(f"  ✗ {rel}: {e}")

    print(f"\nStage 1 complete: {stats['converted']} converted, {stats['skipped']} skipped, {stats['failed']} failed")
    return stats


def run_stage2_graphify(corpus: Path, out_dir: Path) -> dict:
    """Stage 2: Build knowledge graph with graphify.

    Semantic extraction of documents needs an LLM. Inside Claude Code use the
    /graphify skill on <source>/corpus (see SKILL.md, Stage 2); this CLI call only
    works headless when a Gemini key is configured.
    """
    print("\n=== Stage 2: Graphify Knowledge Graph ===\n")

    stats = {"nodes": 0, "edges": 0, "communities": 0}

    graph_file = out_dir / "graph.json"
    if not graph_file.exists():
        cmd = ["graphify", str(corpus)]
        try:
            # cwd=corpus so graphify-out/ lands where Stage 3 expects it
            result = subprocess.run(cmd, capture_output=True, timeout=600, cwd=str(corpus))
            print(result.stdout.decode("utf-8", errors="ignore")[:2000])
        except Exception as e:
            print(f"graphify CLI failed: {e}")
            return stats

    # Load result
    if graph_file.exists():
        try:
            data = json.loads(graph_file.read_text(encoding="utf-8"))
            stats["nodes"] = len(data.get("nodes", []))
            stats["edges"] = len(data.get("links", data.get("edges", [])))
            # Count communities
            comms = set()
            for n in data.get("nodes", []):
                comms.add(str(n.get("community", "")))
            stats["communities"] = len(comms)
        except Exception as e:
            print(f"Failed to parse graph.json: {e}")
    else:
        print(f"graph.json not found at {graph_file}; run the /graphify skill on {corpus}")

    print(f"\nStage 2 complete: {stats['nodes']} nodes, {stats['edges']} edges, {stats['communities']} communities")
    return stats


def clean_filename(name: str) -> str:
    """Make filename safe for Obsidian."""
    return re.sub(UNSAFE_CHARS, "_", name)


def yaml_str(s) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def link_text(s) -> str:
    """Wikilink alias text: no pipes or brackets."""
    return re.sub(r"[|\[\]]", " ", str(s))


def copy_documents(source: Path, corpus: Path, docs_dir: Path) -> int:
    """Copy original documents and their Markdown conversions into the vault.

    Only real source files are copied; generated folders (corpus/, graphify-out/,
    obsidian-vault/) are excluded so the vault never copies itself.
    Files are named by basename, so names match graph.json source_file values.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    candidates = [f for f in source.rglob("*") if f.is_file() and not is_generated(f, source)]
    candidates += [f for f in corpus.rglob("*.md") if "graphify-out" not in f.relative_to(corpus).parts]

    for src in candidates:
        dest = docs_dir / clean_filename(src.name)
        if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
            try:
                shutil.copy2(src, dest)
                count += 1
            except Exception as e:
                print(f"  ✗ copy {src.name}: {e}")

    return count


def extract_relevant_section(content: str, entity_name: str, location: str = "",
                             max_lines: int = 50) -> tuple[str, int]:
    """Return (excerpt, 1-based line of first match or 0) around the entity mention."""
    if not content:
        return "", 0

    lines = content.split("\n")
    words = sorted(re.split(r"[\s/(),:;-]+", entity_name), key=len, reverse=True)

    best_idx = -1
    for needle in [entity_name, location] + words:
        needle = (needle or "").strip().lower()
        if len(needle) < 4:
            continue
        for i, line in enumerate(lines):
            if needle in line.lower():
                best_idx = i
                break
        if best_idx >= 0:
            break

    start = max(0, best_idx - 5) if best_idx >= 0 else 0
    section = "\n".join(lines[start:start + max_lines]).strip()
    # Keep the excerpt from breaking the note: escape headings and code fences
    section = re.sub(r"^(#+)", lambda m: "\\" + m.group(1), section, flags=re.M).replace("```", "'''")
    return section, best_idx + 1 if best_idx >= 0 else 0


def load_graph(graph_file: Path):
    import networkx as nx

    data = json.loads(graph_file.read_text(encoding="utf-8"))
    links_key = "links" if "links" in data else "edges"
    try:
        G = nx.node_link_graph(data, edges=links_key)
    except TypeError:  # networkx < 3.4
        G = nx.node_link_graph(data, link=links_key)
    return G, data, links_key


def run_stage3_obsidian(corpus: Path, vault: Path, source_root: Path) -> dict:
    """Stage 3: Build enhanced Obsidian vault.

    graphify's to_obsidian/to_canvas scaffold the notes and canvas; each node note is
    then rewritten in place (same filename, so canvas cards and links still resolve)
    with the original-document excerpt and directed connections.
    """
    print("\n=== Stage 3: Obsidian Vault Construction ===\n")

    stats = {"notes": 0, "docs_copied": 0, "errors": 0}

    try:
        from graphify import export as gx
    except ImportError:
        print("ERROR: graphify is not importable from this interpreter.")
        print("Run this script with graphify's Python (e.g. %APPDATA%\\uv\\tools\\graphifyy\\Scripts\\python.exe).")
        return stats

    graph_file = corpus / "graphify-out" / "graph.json"
    if not graph_file.exists():
        print(f"ERROR: graph.json not found at {graph_file}")
        return stats

    # Step 1: Copy original documents before writing any note
    print("Copying original documents...")
    docs_dir = vault / "_documentos_originais"
    stats["docs_copied"] = copy_documents(source_root, corpus, docs_dir)
    print(f"  Copied {stats['docs_copied']} documents")

    # Step 2: Load graph data
    G, data, links_key = load_graph(graph_file)
    communities = defaultdict(list)
    for nid, d in G.nodes(data=True):
        if d.get("community") is not None:
            communities[int(d["community"])].append(nid)
    communities = dict(communities)

    labels_file = corpus / "graphify-out" / ".graphify_labels.json"
    community_labels = {}
    if labels_file.exists():
        community_labels = {int(k): v for k, v in
                            json.loads(labels_file.read_text(encoding="utf-8")).items()}

    print(f"Found {G.number_of_nodes()} nodes, {len(data[links_key])} edges, {len(communities)} communities")

    # Step 3: Scaffold with graphify (node notes, community notes, canvas)
    print("Scaffolding vault with graphify...")
    gx.to_obsidian(G, communities, str(vault), community_labels=community_labels or None)
    gx.to_canvas(G, communities, str(vault / "graph.canvas"), community_labels=community_labels or None)
    # Same filename mapping graphify used, so our links match its notes and canvas
    stem_limit = gx.stem_filename_budget(vault, reserve=gx._DEDUP_SUFFIX_RESERVE)
    node_filename = gx._dedup_node_filenames(G, lambda lab: gx._obsidian_safe_stem(lab, stem_limit))

    # Directed connections come from graph.json links (G itself is undirected)
    out_edges, in_edges = defaultdict(list), defaultdict(list)
    for e in data[links_key]:
        s, t = e.get("_src", e["source"]), e.get("_tgt", e["target"])
        out_edges[s].append((t, e))
        in_edges[t].append((s, e))

    # Step 4: Rewrite each node note with embedded content
    print("Building enhanced notes...")
    md_cache = {}
    for node_id, node in G.nodes(data=True):
        label = node.get("label", node_id)
        cid = node.get("community")
        community = (community_labels.get(int(cid), f"Community {cid}")
                     if cid is not None else "sem comunidade")
        entity_type = node.get("file_type", "concept")
        location = str(node.get("source_location") or "")

        src_name = Path(str(node.get("source_file", ""))).name
        md_name = clean_filename(src_name if src_name.endswith(".md") else src_name + ".md") if src_name else ""
        orig_name = clean_filename(src_name[:-3] if src_name.endswith(".md") else src_name)

        if md_name and md_name not in md_cache:
            p = docs_dir / md_name
            md_cache[md_name] = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        relevant, line_no = extract_relevant_section(md_cache.get(md_name, ""), label, location)
        n_conn = len(out_edges[node_id]) + len(in_edges[node_id])

        lines = ["---", "type: graph-note", f'id: "{yaml_str(node_id)}"', f'label: "{yaml_str(label)}"',
                 f"entity_type: {entity_type}", f'community: "{yaml_str(community)}"',
                 f'source_file: "_documentos_originais/{yaml_str(md_name)}"']
        if location:
            lines.append(f'location: "{yaml_str(location)}"')
        lines += ["tags:", f"  - graphify/{entity_type}", f"  - community/{gx._obsidian_tag(community)}",
                  "---", "", f"# {label}", "", f"📍 **Comunidade:** {community}", ""]
        if node.get("rationale"):
            lines += [f"> **Rationale:** {node['rationale']}", ""]

        lines += ["## 📄 Fonte Original", ""]
        if src_name:
            if (docs_dir / orig_name).exists() and orig_name != md_name:
                lines.append(f"- Original: [[_documentos_originais/{orig_name}|{link_text(orig_name)}]]")
            lines.append(f"- Markdown: [[_documentos_originais/{md_name}|{link_text(md_name)}]]")
            if location:
                lines.append(f"- Seção: {location}")
        else:
            lines.append("_Sem documento de origem._")

        lines += ["", "## 📖 Conteúdo Relevante Extraído", ""]
        if relevant:
            lines.append(f"_Trecho a partir da linha {line_no} de `{md_name}`:_" if line_no
                         else f"_Entidade não localizada literalmente; início de `{md_name}`:_")
            lines += [""] + ["> " + x for x in relevant.splitlines()]
        else:
            lines.append("_Conteúdo não encontrado no documento original._")

        lines += ["", f"## 🔗 Conexões ({n_conn})", ""]
        for title, items, arrow in (("### → Conexões de saída", out_edges[node_id], "→"),
                                     ("### ← Conexões de entrada", in_edges[node_id], "←")):
            items = [(o, e) for o, e in items if o in node_filename]
            if not items:
                continue
            lines += [title, ""]
            for other, e in sorted(items, key=lambda x: G.nodes[x[0]].get("label", x[0])):
                other_label = G.nodes[other].get("label", other)
                lines.append(f"- {arrow} [[{node_filename[other]}|{link_text(other_label)}]] — "
                             f"`{e.get('relation', 'related')}` [{e.get('confidence', '')}]")
            lines.append("")
        if not n_conn:
            lines.append("_Sem conexões registradas._")

        lines += ["", "## 📋 Metadados", "", "| Campo | Valor |", "|-------|-------|",
                  f"| Tipo | {entity_type} |", f"| Comunidade | {community} |",
                  f"| Conexões | {n_conn} |", f"| ID | `{node_id}` |"]

        try:
            (vault / f"{node_filename[node_id]}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            stats["notes"] += 1
        except Exception as e:
            stats["errors"] += 1
            print(f"  ✗ {node_id}: {e}")

    # Step 5: Build index
    print("Building index...")
    build_index(vault, corpus, G, communities, community_labels, node_filename)

    print(f"\nStage 3 complete: {stats['notes']} notes created, {stats['docs_copied']} docs copied, "
          f"{stats['errors']} errors")
    return stats


def build_index(vault: Path, corpus: Path, G, communities, community_labels, node_filename):
    """Build the index.md with overview."""
    def link(nid):
        return f"[[{node_filename[nid]}|{link_text(G.nodes[nid].get('label', nid))}]]"

    docs = sorted(f for f in corpus.rglob("*.md") if "graphify-out" not in f.relative_to(corpus).parts)
    index = ["# Knowledge Graph Vault", "",
             "Gerado por Workflow_Digestion: **MarkItDown → Graphify → Obsidian**.", "",
             "## 📊 Estatísticas", "",
             f"- **Nós:** {G.number_of_nodes()}", f"- **Arestas:** {G.number_of_edges()}",
             f"- **Comunidades:** {len(communities)}", f"- **Documentos:** {len(docs)}", "",
             "Visão gráfica: [[graph.canvas]]", "", "## ⭐ Entidades mais conectadas", ""]
    for nid, deg in sorted(G.degree, key=lambda kv: -kv[1])[:10]:
        index.append(f"- {link(nid)} ({deg})")

    index += ["", "## 📂 Comunidades", ""]
    for cid in sorted(communities, key=lambda c: -len(communities[c])):
        members = sorted(communities[cid], key=lambda n: -G.degree(n))
        index += [f"### {community_labels.get(cid, f'Community {cid}')}", f"_{len(members)} entidades_", ""]
        index += [f"- {link(n)}" for n in members[:8]]
        if len(members) > 8:
            index.append(f"- … e mais {len(members) - 8}")
        index.append("")

    index += ["## 📄 Documentos originais", ""]
    docs_dir = vault / "_documentos_originais"
    for f in docs:
        md, orig = clean_filename(f.name), clean_filename(f.name[:-3])
        line = f"- [[_documentos_originais/{md}|{link_text(f.name[:-3])}]]"
        if (docs_dir / orig).exists():
            line += f" · [[_documentos_originais/{orig}|original]]"
        index.append(line)

    (vault / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Workflow_Digestion: markitdown -> graphify -> obsidian")
    parser.add_argument("source", nargs="?", default=".",
                        help="Source folder (defaults to current dir)")
    parser.add_argument("--target", help="Vault output path (defaults to <source>/obsidian-vault)")
    parser.add_argument("--skip-markitdown", action="store_true",
                        help="Skip Stage 1 (use existing corpus)")
    parser.add_argument("--skip-graphify", action="store_true",
                        help="Skip Stage 2 (use existing graph)")
    parser.add_argument("--skip-obsidian", action="store_true",
                        help="Skip Stage 3")

    args = parser.parse_args()

    # Windows consoles default to cp1252, which cannot print ✓/✗/→
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    source = Path(args.source).resolve()
    corpus = source / "corpus"
    vault = Path(args.target).resolve() if args.target else source / "obsidian-vault"

    print(f"Source: {source}")
    print(f"Corpus: {corpus}")
    print(f"Vault: {vault}")

    if not source.exists():
        print(f"ERROR: Source folder does not exist: {source}")
        sys.exit(1)

    # Stage 1
    if not args.skip_markitdown:
        corpus.mkdir(exist_ok=True)
        run_stage1_markitdown(source, corpus)
    else:
        print("Skipping Stage 1 (using existing corpus)")

    # Stage 2
    if not args.skip_graphify:
        run_stage2_graphify(corpus, corpus / "graphify-out")
    else:
        print("Skipping Stage 2 (using existing graph)")

    # Stage 3
    if not args.skip_obsidian:
        vault.mkdir(parents=True, exist_ok=True)
        run_stage3_obsidian(corpus, vault, source)
    else:
        print("Skipping Stage 3")

    print("\n=== Pipeline Complete ===")
    print(f"Vault ready at: {vault}")
    print(f"Open {vault} as a vault in Obsidian to explore.")


if __name__ == "__main__":
    main()
