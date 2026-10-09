#!/usr/bin/env python3
"""
Workflow_Digestion runner: executes the full markitdown -> graphify -> obsidian pipeline.

Usage:
    python run_pipeline.py [source_folder] [--target <vault_path>]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


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
                  ".xml", ".epub"}

    files = []
    for ext in extensions:
        files.extend(source.rglob(f"*{ext}"))

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

        try:
            cmd = ["markitdown", str(src), "-o", str(out)]
            result = subprocess.run(cmd, capture_output=True, timeout=60)

            if result.returncode == 0 and out.exists():
                stats["converted"] += 1
                print(f"  ✓ {rel}")
            else:
                stats["failed"] += 1
                print(f"  ✗ {rel}: {result.stderr.decode()[:100]}")
        except subprocess.TimeoutExpired:
            stats["failed"] += 1
            print(f"  ✗ {rel}: timeout")
        except FileNotFoundError:
            # Try python -m markitdown
            try:
                cmd = ["python", "-m", "markitdown", str(src)]
                result = subprocess.run(cmd, capture_output=True, timeout=60)
                if result.returncode == 0:
                    out.write_text(result.stdout.decode("utf-8", errors="ignore"))
                    stats["converted"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                stats["failed"] += 1
                print(f"  ✗ {rel}: {e}")

    print(f"\nStage 1 complete: {stats['converted']} converted, {stats['skipped']} skipped, {stats['failed']} failed")
    return stats


def run_stage2_graphify(corpus: Path, out_dir: Path) -> dict:
    """Stage 2: Build knowledge graph with graphify."""
    print("\n=== Stage 2: Graphify Knowledge Graph ===\n")

    stats = {"nodes": 0, "edges": 0, "communities": 0}

    # Run graphify CLI
    cmd = ["graphify", str(corpus)]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        print(result.stdout.decode("utf-8", errors="ignore")[:2000])
    except Exception as e:
        print(f"graphify CLI failed: {e}")
        print("Trying python -m graphify...")
        try:
            result = subprocess.run(
                ["python", "-m", "graphify", str(corpus)],
                capture_output=True, timeout=600
            )
            print(result.stdout.decode("utf-8", errors="ignore")[:2000])
        except Exception as e2:
            print(f"Both attempts failed: {e2}")
            return stats

    # Load result
    graph_file = corpus / "graphify-out" / "graph.json"
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

    print(f"\nStage 2 complete: {stats['nodes']} nodes, {stats['edges']} edges, {stats['communities']} communities")
    return stats


def clean_filename(name: str) -> str:
    """Make filename safe for Obsidian."""
    return re.sub(r'[*"\\/<>:|?]', '_', name)


def copy_documents(source: Path, vault: Path) -> int:
    """Copy original documents into vault for Obsidian links."""
    docs_dir = vault / "_documentos_originais"
    docs_dir.mkdir(exist_ok=True)

    count = 0
    extensions = {".md", ".pdf", ".docx", ".pptx", ".xlsx", ".jpg", ".png", ".html"}

    for src in source.rglob("*"):
        if src.is_file() and src.suffix.lower() in extensions:
            rel = src.relative_to(source)
            safe = clean_filename(str(rel).replace("/", "__"))
            dest = docs_dir / safe

            if not dest.exists():
                try:
                    shutil.copy2(src, dest)
                    count += 1
                except Exception:
                    pass

    return count


def extract_relevant_section(content: str, entity_name: str, max_chars: int = 2000) -> str:
    """Extract the most relevant section from content based on entity."""
    if not content:
        return ""

    lines = content.split("\n")
    entity_lower = entity_name.lower()

    best_idx = -1
    for i, line in enumerate(lines):
        if entity_lower in line.lower():
            best_idx = i
            break

    if best_idx == -1:
        best_idx = 0

    start = max(0, best_idx - 5)
    end = min(len(lines), best_idx + 50)

    section = "\n".join(lines[start:end])
    return section[:max_chars]


def get_doc_content(docs_dir: Path, source_file: str) -> str:
    """Read content from copied document."""
    if not source_file:
        return ""
    safe_name = source_file.replace("/", "__")
    doc_path = docs_dir / safe_name
    if doc_path.exists():
        try:
            return doc_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return ""


def run_stage3_obsidian(corpus: Path, vault: Path, source_root: Path) -> dict:
    """Stage 3: Build enhanced Obsidian vault."""
    print("\n=== Stage 3: Obsidian Vault Construction ===\n")

    stats = {"notes": 0, "docs_copied": 0, "errors": 0}

    # Step 1: Run graphify export to scaffold
    print("Scaffolding Obsidian vault...")
    try:
        subprocess.run(
            ["graphify", "export", "obsidian", "--dir", str(vault)],
            capture_output=True, timeout=120
        )
    except Exception as e:
        print(f"Scaffolding warning: {e}")

    # Step 2: Copy original documents
    print("Copying original documents...")
    stats["docs_copied"] = copy_documents(source_root, vault)
    print(f"  Copied {stats['docs_copied']} documents")

    # Step 3: Load graph data
    graph_file = corpus / "graphify-out" / "graph.json"
    if not graph_file.exists():
        print(f"ERROR: graph.json not found at {graph_file}")
        return stats

    try:
        data = json.loads(graph_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR reading graph.json: {e}")
        return stats

    nodes = data.get("nodes", [])
    edges = data.get("links", data.get("edges", []))
    nodes_map = {n.get("id", ""): n for n in nodes}

    print(f"Found {len(nodes)} nodes, {len(edges)} edges")

    # Step 4: Clean old notes
    docs_dir = vault / "_documentos_originais"
    for f in vault.glob("*.md"):
        if f.name != "index.md":
            f.unlink()

    # Step 5: Rebuild each note
    print("Building enhanced notes...")
    for node in nodes:
        node_id = node.get("id", "")
        if not node_id:
            continue

        label = node.get("label", "")
        source_file = str(node.get("source_file", ""))
        community = str(node.get("community", ""))

        # Get content
        content = get_doc_content(docs_dir, source_file)
        relevant = extract_relevant_section(content, label)

        # Build connections
        connections_out = []
        connections_in = []
        for e in edges:
            e_src = e.get("source", e.get("from", ""))
            e_tgt = e.get("target", e.get("to", ""))
            rel = e.get("relation", "related")
            if e_src == node_id:
                connections_out.append((e_tgt, rel))
            elif e_tgt == node_id:
                connections_in.append((e_src, rel))

        # Build note content
        safe_filename = source_file.replace("/", "__") if source_file else ""

        note = f"""---
type: graph-note
label: "{label}"
entity_type: {node.get("file_type", "concept")}
community: "{community}"
source_file: "_documentos_originais/{safe_filename}"
---

# {label}

📍 **Comunidade:** {community}

## 📄 Fonte Original

[[_documentos_originais/{safe_filename}|{Path(source_file).name if source_file else 'N/A'}]]

## 📖 Conteúdo Relevante Extraído

{relevant if relevant else "_Conteúdo não encontrado no documento original._"}

## 🔗 Conexões ({len(connections_out) + len(connections_in)})

"""

        if connections_out:
            note += "\n### → Conexões de saída\n\n"
            for target_id, rel in connections_out[:15]:
                target = nodes_map.get(target_id, {})
                target_label = target.get("label", target_id)
                note += f"- → [[{target_id}|{target_label}]] — `{rel}`\n"

        if connections_in:
            note += "\n### ← Conexões de entrada\n\n"
            for src_id, rel in connections_in[:15]:
                src = nodes_map.get(src_id, {})
                src_label = src.get("label", src_id)
                note += f"- ← [[{src_id}|{src_label}]] — `{rel}`\n"

        if not connections_out and not connections_in:
            note += "_Sem conexões registradas._\n"

        note += f"""

## 📋 Metadados

| Campo | Valor |
|-------|-------|
| Tipo | {node.get("file_type", "concept")} |
| Comunidade | {community} |
| Conexões | {len(connections_out) + len(connections_in)} |
| Documento | [[_documentos_originais/{safe_filename}]] |

#graph-note #{community.replace(' ', '_') if community else 'sem-comunidade'}
"""

        # Save note
        safe_name = clean_filename(node_id)[:200]
        note_path = vault / f"{safe_name}.md"
        try:
            note_path.write_text(note, encoding="utf-8")
            stats["notes"] += 1
        except Exception as e:
            stats["errors"] += 1

    # Step 6: Build index
    print("Building index...")
    build_index(vault, corpus, nodes, edges, nodes_map)

    # Step 7: Regenerate canvas
    print("Regenerating canvas...")
    try:
        subprocess.run(
            ["graphify", "export", "obsidian", "--dir", str(vault)],
            capture_output=True, timeout=120
        )
    except Exception:
        pass

    print(f"\nStage 3 complete: {stats['notes']} notes created, {stats['docs_copied']} docs copied")
    return stats


def build_index(vault: Path, corpus: Path, nodes, edges, nodes_map):
    """Build the index.md with overview."""
    # Group by community
    comm_nodes = {}
    for n in nodes:
        comm = str(n.get("community", ""))
        if comm not in comm_nodes:
            comm_nodes[comm] = []
        comm_nodes[comm].append(n)

    index = """# Knowledge Graph Vault

## 📚 Generated by Workflow_Digestion

This vault was built from the source documents using:
1. **MarkItDown** - file conversion to Markdown
2. **Graphify** - knowledge graph extraction
3. **Obsidian** - navigable vault with embedded content

---

## 📊 Statistics

- **Nodes:** {total_nodes}
- **Edges:** {total_edges}
- **Communities:** {total_communities}

---

## ⭐ Most Connected Entities

""".format(
        total_nodes=len(nodes),
        total_edges=len(edges),
        total_communities=len(comm_nodes)
    )

    degree = {}
    for e in edges:
        for key in ("source", "target"):
            nid = e.get(key, "")
            degree[nid] = degree.get(nid, 0) + 1
    for nid, deg in sorted(degree.items(), key=lambda kv: -kv[1])[:10]:
        if nid in nodes_map:
            index += f"- [[{nid}|{nodes_map[nid].get('label', nid)}]] ({deg})\n"

    index += "\n---\n\n## 📂 Communities\n\n"

    # Community names written by graphify, if present
    community_labels = {}
    labels_file = corpus / "graphify-out" / ".graphify_labels.json"
    if labels_file.exists():
        try:
            community_labels = {str(k): v for k, v in json.loads(
                labels_file.read_text(encoding="utf-8")).items()}
        except Exception:
            pass

    for comm_id in sorted(comm_nodes.keys(),
                          key=lambda x: int(x) if str(x).isdigit() else 999)[:10]:
        label = community_labels.get(str(comm_id), f"Community {comm_id}")
        nl = comm_nodes[comm_id]

        index += f"\n### {label}\n_{len(nl)} entities_\n\n"
        for n in nl[:8]:
            index += f"- [[{n['id']}|{n.get('label', '')}]]\n"
        if len(nl) > 8:
            index += f"- ... and {len(nl) - 8} more\n"

    index += """

---

## 📄 Original Documents

Documents are copied to `_documentos_originais/`:

"""

    docs_dir = vault / "_documentos_originais"
    if docs_dir.exists():
        for doc in sorted(docs_dir.glob("*.md"))[:20]:
            index += f"- [[_documentos_originais/{doc.name}|{doc.stem}]]\n"

    index += "\n---\n\n*Generated by Workflow_Digestion*\n"

    (vault / "index.md").write_text(index, encoding="utf-8")


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
        vault.mkdir(exist_ok=True)
        run_stage3_obsidian(corpus, vault, source)
    else:
        print("Skipping Stage 3")

    print("\n=== Pipeline Complete ===")
    print(f"Vault ready at: {vault}")
    print(f"Open {vault} as a vault in Obsidian to explore.")


if __name__ == "__main__":
    main()