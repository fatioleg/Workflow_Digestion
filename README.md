# Workflow_Digestion

> **MarkItDown → Graphify → Obsidian**: transforme uma pasta de documentos mistos (PDF, DOCX, PPTX, XLSX, imagens, áudio…) em um **vault do Obsidian navegável**, sustentado por um **grafo de conhecimento** explícito.

Workflow_Digestion é um **plugin** para [Claude Code](https://claude.com/claude-code), [Codex CLI](https://github.com/openai/codex) e [Antigravity](https://antigravity.google) (`agy`). Ele "digere" um conjunto heterogêneo de arquivos em três etapas encadeadas:

```
[Pasta de entrada] ──> 1. MarkItDown ──> corpus/*.md
                                           │
                        2. Graphify  <─────┘ ──> graphify-out/graph.json, GRAPH_REPORT.md, graph.html
                                           │
                        3. Obsidian  <─────┘ ──> obsidian-vault/ (notas + links + canvas + índice)
```

---

## ✨ O que ele faz

| Etapa | Ferramenta | Resultado |
|-------|-----------|-----------|
| **1. Conversão** | [MarkItDown](https://github.com/microsoft/markitdown) | Converte cada arquivo para Markdown em `corpus/`, espelhando a estrutura de pastas original. Execução idempotente (só reconverte o que mudou). |
| **2. Grafo** | [Graphify](https://github.com/Graphify-Labs/graphify) | Extrai entidades e relações, detecta comunidades, aponta *god nodes* e conexões surpreendentes. Gera `graph.json`, um relatório de auditoria e uma visualização HTML interativa. |
| **3. Vault** | [Obsidian](https://obsidian.md) | Cria uma nota por entidade **com o trecho relevante do documento original embutido**, links bidirecionais (→ saída / ← entrada), cópia dos documentos originais, `graph.canvas` e um `index.md` com estatísticas, entidades mais conectadas e visão geral das comunidades. |

### Por que não usar só `graphify export obsidian`?

O export nativo gera notas "esqueleto", só com metadados. A etapa 3 deste plugin **lê o documento de origem de cada entidade e embute o conteúdo onde ela é mencionada**. Assim, cada nota já pode ser lida por si só, sem precisar abrir o arquivo original.

---

## 📦 Instalação

### 1. Dependências (uma vez, para qualquer agente)

```bash
pip install 'markitdown[all]'   # etapa 1: conversão de PDF/Office/imagens/áudio
uv tool install graphifyy       # etapa 2: CLI do graphify (ou: pip install graphifyy)
```

- OCR em imagens requer `pytesseract` + Tesseract instalado.
- [Obsidian](https://obsidian.md) para abrir o vault.

### 2. Skill do graphify no seu agente

A etapa 2 precisa de um LLM para a extração semântica dos documentos. O `graphify` sozinho, pela linha de comando, só extrai código; com documentos ele não gera `graph.json`. Instale a skill do graphify no(s) agente(s) que você usa, para que o próprio modelo do agente faça a extração:

```bash
graphify install --platform claude        # Claude Code
graphify install --platform codex         # Codex CLI
graphify install --platform antigravity   # Antigravity (agy)
```

Alternativa sem agente: `graphify extract ./corpus --backend claude` (ou `gemini`, `openai`, …), com a chave de API correspondente definida (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …).

### 3. Instalar o plugin

Este repositório é ao mesmo tempo o plugin e o seu próprio marketplace.

#### Claude Code

Dentro do Claude Code:

```
/plugin marketplace add fatioleg/Workflow_Digestion
/plugin install workflow-digestion@workflow-digestion-marketplace
```

Ou pelo terminal:

```bash
claude plugin marketplace add fatioleg/Workflow_Digestion
claude plugin install workflow-digestion@workflow-digestion-marketplace
```

Reinicie a sessão. A skill aparece como `workflow-digestion:workflow-digestion` e o comando como `/workflow-digestion:digest`.

#### Codex CLI

```bash
codex plugin marketplace add fatioleg/Workflow_Digestion
codex plugin add workflow-digestion@workflow-digestion-marketplace
codex plugin list    # deve mostrar: installed, enabled
```

#### Antigravity (`agy`)

O `agy plugin install` recebe uma pasta local, então clone primeiro:

```bash
git clone https://github.com/fatioleg/Workflow_Digestion
agy plugin validate ./Workflow_Digestion
agy plugin install ./Workflow_Digestion
agy plugin list      # deve mostrar: workflow-digestion (enabled)
```

#### Atualizar / remover

| Agente | Atualizar | Remover |
|--------|-----------|---------|
| Claude Code | `claude plugin marketplace update workflow-digestion-marketplace` e `claude plugin update workflow-digestion@workflow-digestion-marketplace` | `claude plugin uninstall workflow-digestion@workflow-digestion-marketplace` |
| Codex | `codex plugin marketplace upgrade` | `codex plugin remove workflow-digestion@workflow-digestion-marketplace` |
| Antigravity | `git pull` no clone + `agy plugin install ./Workflow_Digestion` | `agy plugin uninstall workflow-digestion` |

> **Migrando da versão skill:** se você instalou antes com `git clone … ~/.claude/skills/Workflow_Digestion`, apague essa pasta para não ter a skill duplicada.

---

## 🚀 Uso

### Dentro do agente

Peça em linguagem natural, por exemplo:

> "Aplique markitdown, depois graphify, depois Obsidian na pasta `./documentos`"

No Claude Code também dá para usar o comando direto:

```
/workflow-digestion:digest ./documentos
```

Na etapa 2, o agente usa a skill `graphify` para fazer a extração semântica (no Claude Code, com subagentes em paralelo).

### Como script standalone

```bash
python skills/workflow-digestion/scripts/run_pipeline.py <pasta_de_origem> [--target <caminho_do_vault>]
```

A etapa 3 importa `graphify`, então rode com o Python do próprio graphify (por exemplo `%APPDATA%\uv\tools\graphifyy\Scripts\python.exe` no Windows). Sem agente, a etapa 2 só funciona com a rota `graphify extract --backend …` descrita acima.

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
| [`skills/workflow-digestion/SKILL.md`](skills/workflow-digestion/SKILL.md) | Instruções da skill (comuns aos três agentes) |
| [`skills/workflow-digestion/scripts/run_pipeline.py`](skills/workflow-digestion/scripts/run_pipeline.py) | Runner standalone das três etapas |
| [`commands/digest.md`](commands/digest.md) | Comando `/workflow-digestion:digest` (Claude Code) |
| [`.claude-plugin/`](.claude-plugin/) | Manifesto e marketplace do Claude Code |
| [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json), [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) | Manifesto e marketplace do Codex |
| [`.antigravity-plugin/plugin.json`](.antigravity-plugin/plugin.json) | Manifesto do Antigravity |

## Licença

[MIT](LICENSE)
