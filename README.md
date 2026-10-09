# Workflow_Digestion

> **MarkItDown → Graphify → Obsidian**: transforme uma pasta de documentos mistos (PDF, DOCX, PPTX, XLSX, imagens, áudio…) em um **vault do Obsidian navegável**, sustentado por um **grafo de conhecimento** explícito.

Workflow_Digestion é uma *skill* para o [Claude Code](https://claude.com/claude-code). Ela "digere" um conjunto heterogêneo de arquivos em três etapas encadeadas:

```
[Pasta de entrada] ──> 1. MarkItDown ──> corpus/*.md
                                           │
                        2. Graphify  <─────┘ ──> graphify-out/graph.json, GRAPH_REPORT.md, graph.html
                                           │
                        3. Obsidian  <─────┘ ──> obsidian-vault/ (notas + links + canvas + índice)
```

---

## ✨ O que ela faz

| Etapa | Ferramenta | Resultado |
|-------|-----------|-----------|
| **1. Conversão** | [MarkItDown](https://github.com/microsoft/markitdown) | Converte cada arquivo para Markdown em `corpus/`, espelhando a estrutura de pastas original. Execução idempotente (só reconverte o que mudou). |
| **2. Grafo** | [Graphify](https://github.com/Graphify-Labs/graphify) | Extrai entidades e relações, detecta comunidades, aponta *god nodes* e conexões surpreendentes. Gera `graph.json`, um relatório de auditoria e uma visualização HTML interativa. |
| **3. Vault** | [Obsidian](https://obsidian.md) | Cria uma nota por entidade **com o trecho relevante do documento original embutido**, links bidirecionais (→ saída / ← entrada), cópia dos documentos originais, `graph.canvas` e um `index.md` com estatísticas, entidades mais conectadas e visão geral das comunidades. |

### Por que não usar só `graphify export obsidian`?

O export nativo gera notas "esqueleto", só com metadados. A etapa 3 desta skill **lê o documento de origem de cada entidade e embute o conteúdo onde ela é mencionada**. Assim, cada nota já pode ser lida por si só, sem precisar abrir o arquivo original.

---

## 📦 Instalação

### 1. Dependências

```bash
pip install 'markitdown[all]'   # conversão de PDF/Office/imagens/áudio
pip install graphifyy           # CLI do graphify
```

- OCR em imagens requer `pytesseract` + Tesseract instalado.
- [Obsidian](https://obsidian.md) para abrir o vault.

### 2. Instalar a skill no Claude Code

```bash
# Linux / macOS
git clone https://github.com/fatioleg/Workflow_Digestion ~/.claude/skills/Workflow_Digestion

# Windows (PowerShell)
git clone https://github.com/fatioleg/Workflow_Digestion "$env:USERPROFILE\.claude\skills\Workflow_Digestion"
```

Reinicie o Claude Code. A skill aparecerá como `workflow-digestion`.

---

## 🚀 Uso

### Dentro do Claude Code

Peça em linguagem natural, por exemplo:

> "Aplique markitdown, depois graphify, depois Obsidian na pasta `./documentos`"

ou invoque diretamente com `/workflow-digestion`.

Na etapa 2, o Claude usa a skill `graphify` para fazer a extração semântica com subagentes em paralelo.

### Como script standalone

```bash
python scripts/run_pipeline.py <pasta_de_origem> [--target <caminho_do_vault>]
```

| Opção | Descrição |
|-------|-----------|
| `source` | Pasta de entrada (padrão: `.`) |
| `--target` | Onde criar o vault (padrão: `<source>/obsidian-vault`) |
| `--skip-markitdown` | Pula a etapa 1 (usa o `corpus/` existente) |
| `--skip-graphify` | Pula a etapa 2 (usa o `graph.json` existente) |
| `--skip-obsidian` | Pula a etapa 3 |

---

## 📁 Estrutura gerada

```
<source>/
├── corpus/                      # Etapa 1: Markdown de cada arquivo
│   └── graphify-out/            # Etapa 2: grafo de conhecimento
│       ├── graph.json
│       ├── GRAPH_REPORT.md
│       └── graph.html
└── obsidian-vault/              # Etapa 3: abra esta pasta no Obsidian
    ├── index.md
    ├── graph.canvas
    ├── <entidade>.md            # uma nota por entidade
    └── _documentos_originais/   # cópias para os links funcionarem
```

### Exemplo de nota de entidade

```markdown
---
type: graph-note
label: "Aspirin"
community: "Drugs"
source_file: "_documentos_originais/a.md"
---

# Aspirin

## 📄 Fonte Original
[[_documentos_originais/a.md|a.md]]

## 📖 Conteúdo Relevante Extraído
...trecho do documento onde a entidade aparece...

## 🔗 Conexões (1)
### → Conexões de saída
- → [[cox|COX]] — `inhibits`
```

---

## 🔁 Quando rodar cada etapa

| Situação | Etapas |
|----------|--------|
| Novos arquivos PDF/Office/imagem | 1 → 2 → 3 |
| Markdown do `corpus/` editado | 2 → 3 |
| Só quer regenerar o vault | 3 |

---

## ⚠️ Cuidados

- Os links do Obsidian usam **caminhos relativos** e nomes de arquivo sanitizados: os caracteres `* " \ / < > : | ?` viram `_`.
- `graph.json` usa `links` (formato NetworkX) para as arestas.
- A etapa 2 consome tokens de LLM (extração semântica). As etapas 1 e 3 são determinísticas.
- O vault copia os documentos originais. **Não publique o vault** se os documentos forem sensíveis.

---

## 📄 Arquivos

| Arquivo | Função |
|---------|--------|
| [`SKILL.md`](SKILL.md) | Instruções da skill lidas pelo Claude Code |
| [`scripts/run_pipeline.py`](scripts/run_pipeline.py) | Runner standalone das três etapas |

## Licença

[MIT](LICENSE)
