---
name: paper-researcher
description: Unified paper discovery, download, Zotero sync, and deep analysis. Fetches daily papers from arXiv/HuggingFace.
version: 2.0.0
metadata:
  openclaw:
    emoji: "🔬"
    requires:
      bins:
        - python3
      pip:
        - pymupdf
        - arxiv
        - requests
        - beautifulsoup4
---

# 🔬 Paper Researcher

Unified skill for: (1) fetching daily papers from arXiv + HuggingFace, (2) downloading PDFs, (3) syncing to Zotero, (4) preparing content for deep analysis.

## Tools

### `fetch_daily_papers` / `update_history`

Fetch new papers (LLM, AI infra, agent, AI security focus), filter by keywords, exclude already-processed ones. Outputs JSON of unprocessed papers.

**Usage:**
```bash
python3 main.py --update-history [--config config/sources_ai_focus.json]
```

**Returns:**
- JSON array of `{title, url, abstract, authors, source}` for new papers.
- If none: `📭 今日暂无新论文`

**Workflow:** Run this first in heartbeat; then for each paper run `research_and_save_paper` with the `url` field.

---

### `research_and_save_paper`

Download paper PDF, sync to Zotero, mark as processed in `papers_history.db`.

**Usage:**
```bash
python3 main.py --url {URL} --dir ./papers
```

**Parameters:**
- `--url`: Paper URL (arXiv or Hugging Face).
- `--dir`: PDF output directory (default `./papers`).

**Returns:**
- Local path to downloaded PDF (or extracted .txt for large files).

## Agent Instructions

1. **Zotero tolerance**: If Zotero sync fails, ignore the error and proceed with analysis.
2. **Two-step flow**:
   - Step A: Run `--update-history` to get new papers.
   - Step B: For each paper, run `--url <url>` then read the PDF/.txt for deep analysis.
3. **History DB**: `papers_history.db` tracks processed papers; `--url` auto-marks on success.

## Config

- `config/sources_ai_focus.json`: LLM, AI infra, agent, AI security keywords.
- `config/sources.json`: Broader default sources.
