import os
import sys
import argparse
import subprocess
import json
import sqlite3
import urllib.request
import urllib.error
import re
import tempfile
import shutil
import time
from datetime import datetime
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# --- History DB ---

def _db_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "papers_history.db")

def _init_db():
    conn = sqlite3.connect(_db_path())
    conn.execute("CREATE TABLE IF NOT EXISTS papers_history (url TEXT PRIMARY KEY, processed_at TEXT)")
    conn.commit()
    return conn

def _canonical_url(paper: dict) -> str:
    """Normalize URL for dedup (arxiv preferred)."""
    if paper.get("source") == "arxiv":
        return paper.get("arxiv_url", paper.get("pdf_url", ""))
    if paper.get("source") == "huggingface":
        url = paper.get("url", "")
        m = re.search(r'huggingface\.co/papers/([^/]+)', url)
        if m:
            return f"https://arxiv.org/abs/{m.group(1)}"
        return url
    return paper.get("url", paper.get("arxiv_url", ""))

def is_processed(url: str) -> bool:
    conn = sqlite3.connect(_db_path())
    row = conn.execute("SELECT 1 FROM papers_history WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is not None

def mark_processed(url: str):
    conn = sqlite3.connect(_db_path())
    conn.execute("INSERT OR IGNORE INTO papers_history (url, processed_at) VALUES (?, ?)",
                 (url, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# --- PDF Downloader Logic (from pdf-paper-read) ---

def get_arxiv_pdf_url(url):
    match = re.search(r'arxiv\.org/abs/([^/]+)', url)
    if match:
        arxiv_id = match.group(1)
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    if 'arxiv.org/pdf/' in url:
        return url
    return None

def get_hf_pdf_url(url):
    match = re.search(r'huggingface\.co/papers/([^/]+)', url)
    if match:
        hf_id = match.group(1)
        return f"https://arxiv.org/pdf/{hf_id}.pdf"
    return None

def download_pdf(pdf_url, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    filename = pdf_url.split('/')[-1].split('?')[0]
    if not filename.endswith('.pdf'):
        filename += '.pdf'
    output_path = os.path.join(output_dir, filename)
    print(f"Downloading {pdf_url}...", file=sys.stderr)
    req = urllib.request.Request(
        pdf_url, 
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response, open(output_path, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        return output_path
    except Exception as e:
        print(f"Error downloading PDF: {e}", file=sys.stderr)
        return None

# --- Zotero Manager Logic (from zotero-manager) ---

def get_arxiv_metadata(url):
    if not url: return None
    match = re.search(r'(?:arxiv\.org/abs/|arxiv\.org/pdf/|huggingface\.co/papers/)([^/]+)', url)
    if not match: return None
    arxiv_id = match.group(1)
    if arxiv_id.endswith('.pdf'):
        arxiv_id = arxiv_id[:-4]
    api_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        with urllib.request.urlopen(api_url, timeout=10) as response:
            content = response.read().decode('utf-8')
            title_match = re.search(r'<entry>.*?<title>(.*?)</title>', content, re.DOTALL)
            title = "Unknown Title"
            if title_match:
                title = " ".join(title_match.group(1).split())
            authors = re.findall(r'<name>(.*?)</name>', content)
            return {"title": title, "authors": authors, "url": url, "arxiv_id": arxiv_id}
    except Exception: return None

def create_ris_content(metadata, file_path):
    ris_content = ["TY  - JOUR"]
    if metadata:
        ris_content.append(f"TI  - {metadata.get('title', 'Unknown Title')}")
        for author in metadata.get('authors', []):
            ris_content.append(f"AU  - {author}")
        if metadata.get('url'):
            ris_content.append(f"UR  - {metadata['url']}")
    else:
        ris_content.append(f"TI  - {os.path.basename(file_path)}")
    abs_path = os.path.abspath(file_path)
    ris_content.append(f"L1  - file://{abs_path}")
    ris_content.append("ER  - ")
    return "\n".join(ris_content)

def stage_file_if_needed(file_path):
    if '.openclaw' in file_path:
        downloads_path = os.path.expanduser("~/Downloads")
        if os.path.exists(downloads_path):
            new_path = os.path.join(downloads_path, os.path.basename(file_path))
            try:
                shutil.copy2(file_path, new_path)
                return new_path
            except Exception: pass
    return file_path

def import_via_bbt(ris_content):
    try:
        url = "http://127.0.0.1:23119/better-bibtex/import"
        data = ris_content.encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200: return True
    except Exception: pass
    return False

def import_via_applescript(ris_path):
    if sys.platform != 'darwin': return False
    try:
        subprocess.run(['open', '-a', 'Zotero', ris_path], check=True)
        time.sleep(1.5)
        cmd = ['osascript', '-e', 'tell application "System Events" to tell process "Zotero" to set frontmost to true', '-e', 'tell application "System Events" to keystroke return']
        subprocess.run(cmd, check=True)
        return True
    except Exception: return False

def import_to_zotero(file_path, url):
    print(f"Attempting to add to Zotero: {file_path}...", file=sys.stderr)
    metadata = get_arxiv_metadata(url)
    staged_file = stage_file_if_needed(file_path)
    ris_text = create_ris_content(metadata, staged_file)
    
    if import_via_bbt(ris_text):
        print("SUCCESS: Imported via Better BibTeX API.", file=sys.stderr)
        return True
    
    safe_name = metadata.get('arxiv_id', 'paper') if metadata else 'paper'
    temp_dir = tempfile.mkdtemp()
    ris_path = os.path.join(temp_dir, f"{safe_name}.ris")
    with open(ris_path, 'w') as f: f.write(ris_text)
    
    if import_via_applescript(ris_path):
        print("SUCCESS: Triggered Zotero via AppleScript.", file=sys.stderr)
        return True
    
    try:
        if sys.platform == 'darwin':
            subprocess.run(['open', '-a', 'Zotero', ris_path], check=True)
        else:
            subprocess.run(['xdg-open', ris_path], check=True)
        print("SUCCESS: Triggered Zotero (manual confirmation needed).", file=sys.stderr)
        return True
    except Exception: return False

def extract_text(pdf_path):
    """Extract text from PDF as a fallback for large files, preventing LLM context overload."""
    if not fitz:
        print("PyMuPDF (fitz) not installed. Cannot extract text.", file=sys.stderr)
        return None
    try:
        text = ""
        with fitz.open(pdf_path) as doc:
            # Extract first 50 pages to avoid context bloat
            for page in doc[:50]:
                text += page.get_text()
        txt_path = pdf_path.replace('.pdf', '.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
        return txt_path
    except Exception as e:
        print(f"Error extracting text: {e}", file=sys.stderr)
        return None

# --- Update History (fetch new papers, output unprocessed as JSON) ---

def _load_config(config_path: str) -> dict:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(script_dir, config_path)
    with open(full_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _filter_papers(papers: list, config: dict) -> list:
    filter_cfg = config.get('filter', {})
    keywords = filter_cfg.get('keywords', [])
    exclude = filter_cfg.get('exclude_keywords', [])
    if not keywords and not exclude:
        return papers
    out = []
    for p in papers:
        text = (p.get('title', '') + ' ' + p.get('abstract', '')).lower()
        if any(k.lower() in text for k in exclude):
            continue
        if keywords and not any(k.lower() in text for k in keywords):
            continue
        out.append(p)
    return out

def _paper_url_for_download(paper: dict) -> str:
    """Return URL suitable for --url (arxiv abs or HF papers page)."""
    if paper.get('source') == 'arxiv':
        return paper.get('arxiv_url', paper.get('pdf_url', ''))
    return paper.get('url', '')

def run_update_history(config_path: str = "config/sources_ai_focus.json") -> list:
    config = _load_config(config_path)
    from arxiv_fetcher import ArxivFetcher
    from huggingface_fetcher import HuggingFaceFetcher

    all_papers = []
    for src in config.get('sources', []):
        if not src.get('enabled'):
            continue
        if src['name'] == 'arxiv':
            cats = src.get('categories', ['cs.AI'])
            max_r = src.get('max_results', 10)
            fetcher = ArxivFetcher(cats, max_r)
            all_papers.extend(fetcher.fetch_daily_papers())
        elif src['name'] == 'huggingface':
            max_r = src.get('max_results', 10)
            fetcher = HuggingFaceFetcher(max_r)
            all_papers.extend(fetcher.fetch_daily_papers())

    filtered = _filter_papers(all_papers, config)
    _init_db()

    new_papers = []
    seen = set()
    for p in filtered:
        url = _canonical_url(p)
        if not url or url in seen:
            continue
        seen.add(url)
        if is_processed(url):
            continue
        entry = {
            'title': p.get('title', ''),
            'url': _paper_url_for_download(p),
            'abstract': p.get('abstract', ''),
            'authors': p.get('authors', []),
            'source': p.get('source', ''),
        }
        new_papers.append(entry)

    return new_papers

# --- Main Logic ---

def main():
    parser = argparse.ArgumentParser(description="Paper Researcher (Hybrid)")
    parser.add_argument("--url", help="Paper URL to read and add to Zotero")
    parser.add_argument("--dir", default="./papers", help="Directory to save PDFs")
    parser.add_argument("--update-history", action="store_true", help="Fetch new papers, output unprocessed as JSON")
    parser.add_argument("--config", default="config/sources_ai_focus.json", help="Config for --update-history")
    args = parser.parse_args()

    if args.update_history:
        new_papers = run_update_history(args.config)
        if not new_papers:
            print("📭 今日暂无新论文")
            sys.exit(0)
        print(json.dumps(new_papers, ensure_ascii=False, indent=2))
        sys.exit(0)

    if not args.url:
        print("Error: --url is required for research mode.", file=sys.stderr)
        sys.exit(1)

    # 1. Resolve and Download
    pdf_url = None
    if 'arxiv.org' in args.url: pdf_url = get_arxiv_pdf_url(args.url)
    elif 'huggingface.co' in args.url: pdf_url = get_hf_pdf_url(args.url)
    
    if not pdf_url:
        if args.url.endswith('.pdf') or '/pdf/' in args.url: pdf_url = args.url
        else:
            print(f"Error: Could not resolve PDF for {args.url}", file=sys.stderr)
            sys.exit(1)
            
    pdf_path = download_pdf(pdf_url, args.dir)
    if not pdf_path:
        print("Error: Download failed.", file=sys.stderr)
        sys.exit(1)
    
    # 2. Add to Zotero (Tolerate errors as requested)
    print("\n[Zotero Sync Phase]", file=sys.stderr)
    zotero_success = import_to_zotero(pdf_path, args.url)
    if not zotero_success:
        print("Notice: Zotero import failed or Zotero is not running. This is normal if Zotero is not installed/open.", file=sys.stderr)
    
    # 3. Mark as processed in history DB
    canonical = args.url
    if 'huggingface.co' in args.url:
        m = re.search(r'huggingface\.co/papers/([^/]+)', args.url)
        if m:
            canonical = f"https://arxiv.org/abs/{m.group(1)}"
    mark_processed(canonical)

    # 4. Output path for the Agent to READ
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if fitz and file_size_mb > 10:
        print(f"Large file detected ({file_size_mb:.2f}MB). Extracting text fallback for Gemini...", file=sys.stderr)
        txt_path = extract_text(pdf_path)
        if txt_path:
            print(f"\nSUCCESS: PDF saved at {pdf_path}, text extracted to {txt_path}")
            print(txt_path)
            sys.exit(0)

    print(f"\nSUCCESS: PDF saved at {pdf_path}")
    print(pdf_path)

if __name__ == "__main__":
    main()
