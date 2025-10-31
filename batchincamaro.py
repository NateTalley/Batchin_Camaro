#!/usr/bin/env python3
# Dataset JSONL Builder + TXT → CSV parser + JSONL → CSV converter
# Features:
# - Batch Inference (CSV → JSONL): Convert CSV to JSONL for batch API calls
# - Finetune modes: Chat, Instruct, Completions (CSV → JSONL)
# - Docs → Batch Inference: Convert documents to JSONL with chunking
# - TXT → CSV: Parse structured text files to CSV with heading detection
# - JSONL → CSV: De-JSONL mode to convert JSONL back to CSV with field selection
# - Separator-line detection for TXT parsing (====, ----, ****, etc.)
# - "Run" button (same as Build Output)

import csv, json, os, re, sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

# Optional readers (for Docs mode)
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except Exception:
    pdf_extract_text = None
try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None
try:
    from striprtf.striprtf import rtf_to_text
except Exception:
    rtf_to_text = None
try:
    import pdf2image
except Exception:
    pdf2image = None
try:
    import pytesseract
except Exception:
    pytesseract = None

APP_TITLE = "🏎️ Batchin' Camaro"
PREVIEW_LINES = 20
DEFAULT_PREFIX = "request-"
MAX_ARRAY_ITEMS_TO_CHECK = 3  # Number of array items to check during field discovery

MODES = [
    "Batch Inference (CSV)",
    "Finetune: Chat",
    "Finetune: Instruct",
    "Finetune: Completions",
    "Docs → Batch Inference",
    "TXT → CSV (parse)",
    "JSONL → CSV (de-JSONL)",
]

DEFAULT_PROMPTS = {
    "Batch Inference (CSV)": "You are a helpful assistant.",
    "Finetune: Chat": "You are a careful, concise assistant. Answer directly. Cite steps briefly when useful.",
    "Finetune: Instruct": "Follow the instruction given as 'input' and produce the best 'output'. Be clear and correct.",
    "Finetune: Completions": "Continue the prompt in a helpful, unambiguous way.",
    "Docs → Batch Inference": (
        "You are a helpful assistant. Use only the provided context to answer. "
        "If the answer isn't in the context, say you don't know."
    ),
}

SUPPORTED_SUFFIXES = {".txt", ".md", ".rst", ".text", ".pdf", ".docx", ".rtf", ".csv"}

@dataclass
class DocumentChunk:
    source: Path
    index: int
    text: str

# ------------------ Text extraction (Docs mode) ------------------
def _extract_pdf_text(path: Path) -> str:
    if pdf_extract_text is None: return ""
    try: return pdf_extract_text(str(path))
    except Exception: return ""

def _extract_docx_text(path: Path) -> str:
    if DocxDocument is None: return ""
    try: doc = DocxDocument(str(path))
    except Exception: return ""
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in getattr(doc, "tables", []):
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells: parts.append(" • ".join(cells))
    return "\n".join(parts)

def _extract_rtf_text(path: Path) -> str:
    if rtf_to_text is None: return ""
    try: data = path.read_bytes()
    except Exception: return ""
    for enc in ("utf-8","latin-1"):
        try: txt = data.decode(enc); break
        except UnicodeDecodeError: continue
    else: txt = data.decode("utf-8", errors="ignore")
    try: return rtf_to_text(txt)
    except Exception: return ""

def _read_csv_text(path: Path) -> str:
    try: data = path.read_bytes()
    except Exception: return ""
    for enc in ("utf-8","utf-16","latin-1"):
        try: txt = data.decode(enc); break
        except UnicodeDecodeError: continue
    else: txt = data.decode("utf-8", errors="ignore")
    rows, reader = [], csv.reader(txt.splitlines())
    for row in reader:
        cleaned = [c.strip() for c in row if c.strip()]
        if cleaned: rows.append(", ".join(cleaned))
    return "\n".join(rows)

def _ocr_pdf(path: Path, *, language="eng", dpi=300) -> str:
    if pdf2image is None or pytesseract is None: return ""
    try: images = pdf2image.convert_from_path(str(path), dpi=dpi)
    except Exception: return ""
    out = []
    for im in images:
        try: out.append(pytesseract.image_to_string(im, lang=language))
        except Exception: pass
    return "\n".join(s.strip() for s in out if s.strip())

def read_document(path: Path, *, enable_ocr: bool, ocr_language: str, ocr_dpi: int) -> str:
    sfx = path.suffix.lower()
    if sfx == ".pdf":
        text = _extract_pdf_text(path)
        if text.strip(): return text
        return _ocr_pdf(path, language=ocr_language, dpi=ocr_dpi) if enable_ocr else ""
    if sfx == ".docx": return _extract_docx_text(path)
    if sfx == ".rtf":  return _extract_rtf_text(path)
    if sfx == ".csv":  return _read_csv_text(path)
    try: return path.read_text(encoding="utf-8")
    except UnicodeDecodeError: return ""

def iter_text_files(root: Path, suffixes) -> list[Path]:
    out = []
    for p in Path(root).rglob("*"):
        if p.is_file() and p.suffix.lower() in suffixes:
            out.append(p)
    return out

# ------------------ Sentence-safe chunking (Docs mode) ------------------
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(])')

def split_paragraphs(text: str) -> list[str]:
    blocks = re.split(r'\n{2,}|\r\n{2,}', text.replace('\r\n','\n'))
    return [b.strip() for b in blocks if b.strip()]

def split_sentences(paragraph: str) -> list[str]:
    parts = _SENT_SPLIT.split(paragraph.strip())
    merged = []
    for s in parts:
        s = s.strip()
        if not s: continue
        if merged and len(s.split()) < 4:
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged

def chunk_sentence_safe(text: str, *, target_words: int, overlap_sents: int, by_paragraph_only: bool) -> list[str]:
    if target_words <= 0: raise ValueError("target_words must be > 0")
    if overlap_sents < 0: overlap_sents = 0
    paras = split_paragraphs(text)
    if not paras: return []
    if by_paragraph_only:
        chunks, buf, count = [], [], 0
        for p in paras:
            w = len(p.split())
            if count and count + w > target_words * 1.2:
                chunks.append(" ".join(buf).strip()); buf, count = [p], w
            else:
                buf.append(p); count += w
        if buf: chunks.append(" ".join(buf).strip())
        return chunks
    chunks, window, window_words = [], [], 0
    for p in paras:
        sents = split_sentences(p)
        for s in sents:
            w = len(s.split())
            if window_words + w > target_words and window:
                chunks.append(" ".join(window).strip())
                window = window[-overlap_sents:] if overlap_sents > 0 else []
                window_words = len(" ".join(window).split()) if window else 0
            window.append(s); window_words += w
        if window_words > target_words * 1.3:
            chunks.append(" ".join(window).strip()); window, window_words = [], 0
    if window: chunks.append(" ".join(window).strip())
    return chunks

# ------------------ TXT → CSV parsing heuristics ------------------
_HEADING_NUM = re.compile(r'^\s*(?:\d+\.|[IVXLC]+\.?)\s+[^\s].*$')  # "1. Title", "II. Title"
# separator lines like "====", "----", "***", "____", "~~~~", or mixed runs of the same char
_SEP_RUN = re.compile(r'^\s*([=\-\*_~#]{3,})\s*$')

def is_separator(line: str, cfg) -> bool:
    if not cfg["split_on_separators"]:
        return False
    s = line.strip()
    if len(s) < cfg["min_separator_len"]:
        return False
    # all same char or matches SEPARATOR RUN pattern
    return (len(set(s)) == 1 and s[0] in "=*-_~#") or bool(_SEP_RUN.match(line))

def is_heading(line: str, next_is_blank: bool, cfg) -> bool:
    s = line.strip()
    if len(s) < cfg["min_heading_chars"] or len(s) > cfg["max_heading_chars"]:
        return False
    if cfg["detect_numbered"] and _HEADING_NUM.match(s):
        return True
    if cfg["detect_all_caps"] and s.isupper() and re.search(r'[A-Z]', s):
        return True
    if cfg["detect_title_case"]:
        words = s.split()
        if words and words[0][0].isupper():
            cap_words = sum(1 for w in words if w[:1].isupper())
            if cap_words >= max(1, int(0.6 * len(words))):
                return True
    return next_is_blank

def parse_txt_to_records(txt: str, cfg) -> list[dict]:
    """
    Returns list of {title, content}. Ignores lines shorter than cfg['min_line_len'].
    Starts a new record when a heading or separator is detected.
    Blank lines separate paragraphs.
    """
    lines = txt.replace('\r\n','\n').split('\n')
    filtered = [ln for ln in lines if len(ln.strip()) >= cfg["min_line_len"] or ln.strip()=="" or is_separator(ln, cfg)]

    records = []
    cur_title = None
    buf = []

    def derive_title_and_content():
        nonlocal cur_title, buf
        title = cur_title
        lines_buf = [b for b in buf if b != ""]
        if title is None and lines_buf:
            first = lines_buf[0].strip()
            if is_heading(first, True, cfg):
                title = first
                # remove first heading line from buf
                drop = True
            else:
                drop = False
        else:
            drop = False

        content_lines = buf.copy()
        if drop and content_lines and content_lines[0].strip():
            content_lines = content_lines[1:]

        # collapse multiple blank lines to single paragraph breaks
        content = "\n".join(p for p in "\n".join(content_lines).split("\n\n") if p.strip()).strip()
        return title or "", content

    def flush():
        nonlocal cur_title, buf
        title, content = derive_title_and_content()
        if title or content:
            records.append({"title": title, "content": content})
        cur_title, buf = None, []

    for i, ln in enumerate(filtered):
        if is_separator(ln, cfg):
            # Separator marks end of current section
            if buf or cur_title:
                flush()
            continue

        nxt_blank = (i+1 < len(filtered) and filtered[i+1].strip() == "")
        if ln.strip() == "":
            if buf and buf[-1] != "": buf.append("")
            continue

        if is_heading(ln, nxt_blank, cfg):
            if buf:
                flush()
            cur_title = ln.strip()
            continue

        buf.append(ln.strip())

    if buf or cur_title:
        flush()

    return [r for r in records if r["title"] or r["content"]]

# ------------------ GUI ------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x780")
        self.minsize(1100, 640)

        # Mode
        self.mode = tk.StringVar(value=MODES[0])
        self.system_prompt = tk.StringVar(value=DEFAULT_PROMPTS.get(self.mode.get(), ""))

        # CSV state
        self.csv_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.rows, self.headers = [], []
        self.content_col = tk.StringVar()
        self.id_col = tk.StringVar(value="<None>")
        self.prefix_id = tk.StringVar(value=DEFAULT_PREFIX)
        # Finetune mappings
        self.assistant_col = tk.StringVar()
        self.instruct_in_col = tk.StringVar()
        self.instruct_out_col = tk.StringVar()
        self.comp_prompt_col = tk.StringVar()
        self.comp_completion_col = tk.StringVar()
        
        # Batch inference parameters
        self.include_params = tk.BooleanVar(value=False)
        self.max_tokens = tk.IntVar(value=256)
        self.temperature = tk.DoubleVar(value=0.8)

        # Docs chunking
        self.docs_dir = tk.StringVar()
        self.target_words = tk.IntVar(value=180)
        self.overlap_sents = tk.IntVar(value=1)
        self.para_only = tk.BooleanVar(value=False)
        self.ocr_enabled = tk.BooleanVar(value=False)
        self.ocr_lang = tk.StringVar(value="eng")
        self.ocr_dpi = tk.IntVar(value=300)
        self.suffix_extra = tk.StringVar(value="")

        # TXT → CSV parsing config
        self.txt_path = tk.StringVar()
        self.min_line_len = tk.IntVar(value=20)
        self.detect_all_caps = tk.BooleanVar(value=True)
        self.detect_title_case = tk.BooleanVar(value=True)
        self.detect_numbered = tk.BooleanVar(value=True)
        self.min_heading_chars = tk.IntVar(value=3)
        self.max_heading_chars = tk.IntVar(value=120)
        self.split_on_separators = tk.BooleanVar(value=True)
        self.min_separator_len = tk.IntVar(value=5)
        # Section selection
        self.start_line = tk.IntVar(value=1)
        self.end_line = tk.IntVar(value=-1)  # -1 means end of file
        self.use_line_range = tk.BooleanVar(value=False)
        # Delimiter control
        self.csv_delimiter = tk.StringVar(value=",")
        # Header handling
        self.has_header_row = tk.BooleanVar(value=False)
        self.skip_header = tk.BooleanVar(value=False)
        self.custom_title_header = tk.StringVar(value="title")
        self.custom_content_header = tk.StringVar(value="content")

        # JSONL → CSV de-JSONL config
        self.jsonl_path = tk.StringVar()
        self.jsonl_fields = {}  # Will store BooleanVar for each discovered field
        self.jsonl_available_fields = []  # List of all available field paths

        # Menu
        mbar = tk.Menu(self)
        filem = tk.Menu(mbar, tearoff=0)
        filem.add_command(label="Open CSV…", command=self.menu_open_csv)
        filem.add_command(label="Open TXT…", command=self.menu_open_txt)
        filem.add_command(label="Open JSONL…", command=self.menu_open_jsonl)
        filem.add_command(label="Save Output As…", command=self.menu_save_output)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        mbar.add_cascade(label="File", menu=filem)
        self.config(menu=mbar)

        # Paned
        self.pw = ttk.Panedwindow(self, orient="horizontal"); self.pw.pack(fill="both", expand=True)
        left, right = ttk.Frame(self.pw), ttk.Frame(self.pw)
        self.pw.add(left, weight=3); self.pw.add(right, weight=2)

        # Mode
        fr_mode = ttk.LabelFrame(left, text="Mode"); fr_mode.pack(fill="x", padx=10, pady=(10,8))
        ttk.Label(fr_mode, text="Select:").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        cb = ttk.Combobox(fr_mode, state="readonly", values=MODES, textvariable=self.mode)
        cb.grid(row=0, column=1, sticky="we", padx=6, pady=6); fr_mode.columnconfigure(1, weight=1)
        cb.bind("<<ComboboxSelected>>", self.on_mode_change)

        # Paths
        fr_paths = ttk.LabelFrame(left, text="Paths"); fr_paths.pack(fill="x", padx=10, pady=8); fr_paths.columnconfigure(1, weight=1)
        # CSV
        self.lbl_in_csv = ttk.Label(fr_paths, text="Input CSV:")
        self.ent_in_csv = ttk.Entry(fr_paths, textvariable=self.csv_path)
        self.btn_in_csv = ttk.Button(fr_paths, text="Open…", command=self.menu_open_csv, width=12)
        # Docs
        self.lbl_docs = ttk.Label(fr_paths, text="Docs folder:")
        self.ent_docs = ttk.Entry(fr_paths, textvariable=self.docs_dir)
        self.btn_docs = ttk.Button(fr_paths, text="Browse…", command=self.browse_docs, width=12)
        # TXT
        self.lbl_txt = ttk.Label(fr_paths, text="Input TXT:")
        self.ent_txt = ttk.Entry(fr_paths, textvariable=self.txt_path)
        self.btn_txt = ttk.Button(fr_paths, text="Open…", command=self.menu_open_txt, width=12)
        # JSONL
        self.lbl_jsonl = ttk.Label(fr_paths, text="Input JSONL:")
        self.ent_jsonl = ttk.Entry(fr_paths, textvariable=self.jsonl_path)
        self.btn_jsonl = ttk.Button(fr_paths, text="Open…", command=self.menu_open_jsonl, width=12)

        ttk.Label(fr_paths, text="Output file:").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_paths, textvariable=self.out_path).grid(row=3, column=1, sticky="we", padx=6, pady=6)
        ttk.Button(fr_paths, text="Save As…", command=self.menu_save_output, width=12).grid(row=3, column=2, padx=6, pady=6)

        # Column mapping
        fr_cols = ttk.LabelFrame(left, text="Column Mapping"); fr_cols.pack(fill="x", padx=10, pady=8); fr_cols.columnconfigure(1, weight=1)
        self.lbl_content = ttk.Label(fr_cols, text="Content column (user):"); self.cb_content = ttk.Combobox(fr_cols, textvariable=self.content_col)
        self.lbl_id = ttk.Label(fr_cols, text="ID column (<None> for prefix):"); self.cb_id = ttk.Combobox(fr_cols, textvariable=self.id_col)
        self.lbl_prefix = ttk.Label(fr_cols, text="If no ID, use prefix:"); self.ent_prefix = ttk.Entry(fr_cols, textvariable=self.prefix_id)
        # Batch inference parameters
        self.chk_params = ttk.Checkbutton(fr_cols, text="Include max_tokens & temperature", variable=self.include_params, command=self.refresh_preview)
        self.lbl_max_tokens = ttk.Label(fr_cols, text="Max tokens:")
        self.ent_max_tokens = ttk.Entry(fr_cols, textvariable=self.max_tokens, width=10)
        self.lbl_temperature = ttk.Label(fr_cols, text="Temperature:")
        self.ent_temperature = ttk.Entry(fr_cols, textvariable=self.temperature, width=10)
        # Finetune mappings
        self.lbl_asst = ttk.Label(fr_cols, text="Assistant column:"); self.cb_asst = ttk.Combobox(fr_cols, textvariable=self.assistant_col)
        self.lbl_in_instruct = ttk.Label(fr_cols, text="Input column:"); self.cb_in_instruct = ttk.Combobox(fr_cols, textvariable=self.instruct_in_col)
        self.lbl_out_instruct = ttk.Label(fr_cols, text="Output column:"); self.cb_out_instruct = ttk.Combobox(fr_cols, textvariable=self.instruct_out_col)
        self.lbl_prompt_comp = ttk.Label(fr_cols, text="Prompt column:"); self.cb_prompt_comp = ttk.Combobox(fr_cols, textvariable=self.comp_prompt_col)
        self.lbl_completion_comp = ttk.Label(fr_cols, text="Completion column:"); self.cb_completion_comp = ttk.Combobox(fr_cols, textvariable=self.comp_completion_col)

        # Docs chunking
        fr_docs = ttk.LabelFrame(left, text="Docs Chunking"); fr_docs.pack(fill="x", padx=10, pady=8)
        for i in (1,3,5): fr_docs.columnconfigure(i, weight=1)
        ttk.Label(fr_docs, text="Target words:").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_docs, textvariable=self.target_words, width=10).grid(row=0, column=1, sticky="w", padx=6, pady=6)
        ttk.Label(fr_docs, text="Sentence overlap:").grid(row=0, column=2, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_docs, textvariable=self.overlap_sents, width=10).grid(row=0, column=3, sticky="w", padx=6, pady=6)
        ttk.Checkbutton(fr_docs, text="Paragraph-only chunks", variable=self.para_only).grid(row=0, column=4, sticky="w", padx=6, pady=6)
        ttk.Checkbutton(fr_docs, text="Enable PDF OCR fallback", variable=self.ocr_enabled).grid(row=1, column=0, sticky="w", padx=6, pady=6)
        ttk.Label(fr_docs, text="OCR lang:").grid(row=1, column=1, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_docs, textvariable=self.ocr_lang, width=10).grid(row=1, column=2, sticky="w", padx=6, pady=6)
        ttk.Label(fr_docs, text="OCR DPI:").grid(row=1, column=3, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_docs, textvariable=self.ocr_dpi, width=10).grid(row=1, column=4, sticky="w", padx=6, pady=6)
        ttk.Label(fr_docs, text="Extra suffixes:").grid(row=1, column=5, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_docs, textvariable=self.suffix_extra).grid(row=1, column=6, sticky="we", padx=6, pady=6)

        # TXT → CSV settings
        fr_txt = ttk.LabelFrame(left, text="TXT → CSV parsing")
        fr_txt.pack(fill="x", padx=10, pady=8)
        for i in (1,3,5): fr_txt.columnconfigure(i, weight=1)
        
        # Row 0: Line filtering and heading detection
        ttk.Label(fr_txt, text="Ignore lines shorter than:").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.min_line_len, width=10).grid(row=0, column=1, sticky="w", padx=6, pady=6)
        ttk.Label(fr_txt, text="Min heading chars:").grid(row=0, column=2, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.min_heading_chars, width=10).grid(row=0, column=3, sticky="w", padx=6, pady=6)
        ttk.Label(fr_txt, text="Max heading chars:").grid(row=0, column=4, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.max_heading_chars, width=10).grid(row=0, column=5, sticky="w", padx=6, pady=6)
        
        # Row 1: Detection options
        ttk.Checkbutton(fr_txt, text="Detect ALL CAPS headings", variable=self.detect_all_caps).grid(row=1, column=0, sticky="w", padx=6, pady=6)
        ttk.Checkbutton(fr_txt, text="Detect Title Case headings", variable=self.detect_title_case).grid(row=1, column=1, sticky="w", padx=6, pady=6)
        ttk.Checkbutton(fr_txt, text="Detect numbered headings", variable=self.detect_numbered).grid(row=1, column=2, sticky="w", padx=6, pady=6)
        ttk.Checkbutton(fr_txt, text="Split on separator lines (====, ----, ***)", variable=self.split_on_separators).grid(row=1, column=3, columnspan=2, sticky="w", padx=6, pady=6)
        ttk.Label(fr_txt, text="Min separator len:").grid(row=1, column=5, sticky="w", padx=6, pady=6)
        
        # Row 2: Section selection
        ttk.Checkbutton(fr_txt, text="Parse specific line range", variable=self.use_line_range).grid(row=2, column=0, sticky="w", padx=6, pady=6)
        ttk.Label(fr_txt, text="Start line:").grid(row=2, column=1, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.start_line, width=10).grid(row=2, column=2, sticky="w", padx=6, pady=6)
        ttk.Label(fr_txt, text="End line (-1=end):").grid(row=2, column=3, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.end_line, width=10).grid(row=2, column=4, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.min_separator_len, width=10).grid(row=2, column=5, sticky="w", padx=6, pady=6)
        
        # Row 3: CSV output delimiter
        ttk.Label(fr_txt, text="CSV delimiter:").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.csv_delimiter, width=10).grid(row=3, column=1, sticky="w", padx=6, pady=6)
        
        # Row 4: Header handling
        ttk.Checkbutton(fr_txt, text="First row is header (skip it)", variable=self.has_header_row).grid(row=4, column=0, sticky="w", padx=6, pady=6)
        ttk.Label(fr_txt, text="Title header name:").grid(row=4, column=1, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.custom_title_header, width=12).grid(row=4, column=2, sticky="w", padx=6, pady=6)
        ttk.Label(fr_txt, text="Content header name:").grid(row=4, column=3, sticky="w", padx=6, pady=6)
        ttk.Entry(fr_txt, textvariable=self.custom_content_header, width=12).grid(row=4, column=4, sticky="w", padx=6, pady=6)

        # JSONL → CSV field selection
        fr_jsonl = ttk.LabelFrame(left, text="JSONL → CSV: Field Selection")
        fr_jsonl.pack(fill="both", expand=False, padx=10, pady=8)
        
        # Buttons at the top
        btn_frame = ttk.Frame(fr_jsonl)
        btn_frame.pack(fill="x", padx=6, pady=6)
        self.jsonl_select_all_btn = ttk.Button(btn_frame, text="Select All", command=self.select_all_jsonl_fields)
        self.jsonl_select_all_btn.pack(side="left", padx=(0, 6))
        self.jsonl_deselect_all_btn = ttk.Button(btn_frame, text="Deselect All", command=self.deselect_all_jsonl_fields)
        self.jsonl_deselect_all_btn.pack(side="left", padx=(0, 6))
        self.jsonl_info_label = ttk.Label(btn_frame, text="Open a JSONL file to see available fields")
        self.jsonl_info_label.pack(side="left", padx=6)
        
        # Scrollable frame for checkboxes
        canvas = tk.Canvas(fr_jsonl, height=150)
        scrollbar = ttk.Scrollbar(fr_jsonl, orient="vertical", command=canvas.yview)
        self.jsonl_fields_frame = ttk.Frame(canvas)
        
        self.jsonl_fields_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.jsonl_fields_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scrollbar.pack(side="right", fill="y", pady=6, padx=(0, 6))

        # Prompt
        fr_prompt = ttk.LabelFrame(left, text="System Prompt (default per mode)")
        fr_prompt.pack(fill="both", expand=True, padx=10, pady=8)
        self.txt_prompt = tk.Text(fr_prompt, height=6, wrap="word")
        self.txt_prompt.pack(fill="both", expand=True, padx=6, pady=6)
        self.txt_prompt.insert("1.0", self.system_prompt.get())

        # Actions
        fr_actions = ttk.Frame(left); fr_actions.pack(fill="x", padx=10, pady=(4,10))
        ttk.Button(fr_actions, text="Run", command=self.build_output).pack(side="right")                 # NEW
        ttk.Button(fr_actions, text="Build Output", command=self.build_output).pack(side="right", padx=8)
        ttk.Button(fr_actions, text="Refresh Preview", command=self.refresh_preview).pack(side="right", padx=8)
        self.status = tk.StringVar(value="Set mode, open source (CSV/docs/txt), choose output, then Run.")
        ttk.Label(left, textvariable=self.status, anchor="w").pack(fill="x", padx=12, pady=(0,10))

        # Right: prefix + preview
        pr = ttk.LabelFrame(right, text=f"Preview (first {PREVIEW_LINES} items — unique parts only)")
        pr.pack(fill="both", expand=True, padx=10, pady=10)
        pr.rowconfigure(2, weight=1); pr.columnconfigure(0, weight=1)

        ttk.Label(pr, text="Common JSON prefix (when applicable) shown once:").grid(row=0, column=0, sticky="w", padx=6, pady=(6,2))
        self.prefix_box = tk.Text(pr, height=6, wrap="none"); self.prefix_box.grid(row=1, column=0, sticky="we", padx=6)
        self.prefix_box.configure(state="disabled")

        self.preview_box = tk.Text(pr, wrap="none", undo=False)
        self.preview_box.grid(row=2, column=0, sticky="nsew", padx=6, pady=(6,6))
        yscroll = ttk.Scrollbar(pr, orient="vertical", command=self.preview_box.yview); yscroll.grid(row=2, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(pr, orient="horizontal", command=self.preview_box.xview); xscroll.grid(row=3, column=0, sticky="ew", padx=6)
        self.preview_box.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        # Add traces to update preview when parameters change
        self.max_tokens.trace_add("write", lambda *args: self.refresh_preview())
        self.temperature.trace_add("write", lambda *args: self.refresh_preview())

        self.layout_for_mode()
        try:
            import ctypes
            if sys.platform.startswith("win"): ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass

    # ----- mode layout -----
    def on_mode_change(self, _=None):
        self.system_prompt.set(DEFAULT_PROMPTS.get(self.mode.get(), ""))
        self.txt_prompt.delete("1.0","end"); self.txt_prompt.insert("1.0", self.system_prompt.get())
        self.layout_for_mode(); self.refresh_preview()

    def layout_for_mode(self):
        for w in (self.lbl_in_csv, self.ent_in_csv, self.btn_in_csv,
                  self.lbl_docs, self.ent_docs, self.btn_docs,
                  self.lbl_txt, self.ent_txt, self.btn_txt,
                  self.lbl_jsonl, self.ent_jsonl, self.btn_jsonl):
            try: w.grid_forget()
            except Exception: pass

        mode = self.mode.get()
        if mode == "Docs → Batch Inference":
            self.lbl_docs.grid(row=0, column=0, sticky="w", padx=6, pady=6)
            self.ent_docs.grid(row=0, column=1, sticky="we", padx=6, pady=6)
            self.btn_docs.grid(row=0, column=2, padx=6, pady=6)
        elif mode == "TXT → CSV (parse)":
            self.lbl_txt.grid(row=0, column=0, sticky="w", padx=6, pady=6)
            self.ent_txt.grid(row=0, column=1, sticky="we", padx=6, pady=6)
            self.btn_txt.grid(row=0, column=2, padx=6, pady=6)
        elif mode == "JSONL → CSV (de-JSONL)":
            self.lbl_jsonl.grid(row=0, column=0, sticky="w", padx=6, pady=6)
            self.ent_jsonl.grid(row=0, column=1, sticky="we", padx=6, pady=6)
            self.btn_jsonl.grid(row=0, column=2, padx=6, pady=6)
        else:
            self.lbl_in_csv.grid(row=0, column=0, sticky="w", padx=6, pady=6)
            self.ent_in_csv.grid(row=0, column=1, sticky="we", padx=6, pady=6)
            self.btn_in_csv.grid(row=0, column=2, padx=6, pady=6)

        for w in (self.lbl_content,self.cb_content,self.lbl_id,self.cb_id,self.lbl_prefix,self.ent_prefix,
                  self.chk_params,self.lbl_max_tokens,self.ent_max_tokens,self.lbl_temperature,self.ent_temperature,
                  self.lbl_asst,self.cb_asst,self.lbl_in_instruct,self.cb_in_instruct,
                  self.lbl_out_instruct,self.cb_out_instruct,self.lbl_prompt_comp,self.cb_prompt_comp,
                  self.lbl_completion_comp,self.cb_completion_comp):
            try: w.grid_forget()
            except Exception: pass

        r=0
        if mode == "Batch Inference (CSV)":
            self.lbl_content.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_content.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
            self.lbl_id.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_id.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
            self.lbl_prefix.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.ent_prefix.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
            self.chk_params.grid(row=r,column=0,columnspan=2,sticky="w",padx=6,pady=6); r+=1
            self.lbl_max_tokens.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.ent_max_tokens.grid(row=r,column=1,sticky="w",padx=6,pady=6); r+=1
            self.lbl_temperature.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.ent_temperature.grid(row=r,column=1,sticky="w",padx=6,pady=6); r+=1
        elif mode == "Finetune: Chat":
            self.lbl_content.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_content.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
            self.lbl_asst.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_asst.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
        elif mode == "Finetune: Instruct":
            self.lbl_in_instruct.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_in_instruct.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
            self.lbl_out_instruct.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_out_instruct.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
        elif mode == "Finetune: Completions":
            self.lbl_prompt_comp.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_prompt_comp.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1
            self.lbl_completion_comp.grid(row=r,column=0,sticky="w",padx=6,pady=6); self.cb_completion_comp.grid(row=r,column=1,sticky="we",padx=6,pady=6); r+=1

        self._set_group_state("Docs Chunking", "normal" if mode=="Docs → Batch Inference" else "disabled")
        self._set_group_state("TXT → CSV parsing", "normal" if mode=="TXT → CSV (parse)" else "disabled")
        self._set_group_state("JSONL → CSV: Field Selection", "normal" if mode=="JSONL → CSV (de-JSONL)" else "disabled")

    def _set_group_state(self, group_title: str, state: str):
        for child in self._children_of_label_frame(group_title):
            try: child.configure(state=state)
            except Exception: pass

    def _children_of_label_frame(self, title: str):
        for child in self.winfo_children():
            if isinstance(child, ttk.Panedwindow):
                for sub in child.winfo_children():
                    for lf in sub.winfo_children():
                        if isinstance(lf, ttk.LabelFrame) and lf.cget("text")==title:
                            return lf.winfo_children()
        return []

    # ----- menu actions -----
    def menu_open_csv(self):
        path = filedialog.askopenfilename(title="Select CSV", filetypes=[("CSV files","*.csv"),("All files","*.*")])
        if not path: return
        self.load_csv(path); self.refresh_preview()

    def menu_open_txt(self):
        path = filedialog.askopenfilename(title="Select TXT", filetypes=[("Text files","*.txt"),("All files","*.*")])
        if not path: return
        self.txt_path.set(path); self.refresh_preview()

    def menu_open_jsonl(self):
        path = filedialog.askopenfilename(title="Select JSONL", filetypes=[("JSON Lines","*.jsonl"),("All files","*.*")])
        if not path: return
        self.load_jsonl(path); self.refresh_preview()

    def menu_save_output(self):
        mode = self.mode.get()
        if mode in ("TXT → CSV (parse)", "JSONL → CSV (de-JSONL)"):
            ftypes = [("CSV files","*.csv"),("All files","*.*")]
            dflt = ".csv"
        else:
            ftypes = [("JSON Lines","*.jsonl"),("All files","*.*")]
            dflt = ".jsonl"
        path = filedialog.asksaveasfilename(title="Save Output", defaultextension=dflt, filetypes=ftypes)
        if path: self.out_path.set(path)

    def browse_docs(self):
        path = filedialog.askdirectory(title="Select documents folder")
        if path: self.docs_dir.set(path); self.refresh_preview()

    # ----- CSV loading -----
    def load_csv(self, path):
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f); self.headers = reader.fieldnames or []; self.rows = list(reader)
            if not self.headers: raise ValueError("No headers found.")
            if not self.rows: raise ValueError("No data rows found.")
        except Exception as e:
            messagebox.showerror("CSV Error", f"Failed to read CSV:\n{e}")
            self.headers, self.rows = [], []
            for cb in (self.cb_content,self.cb_id,self.cb_asst,self.cb_in_instruct,self.cb_out_instruct,self.cb_prompt_comp,self.cb_completion_comp):
                cb.configure(values=[])
            self.status.set("CSV load failed."); return

        self.csv_path.set(path)
        vals = self.headers
        for cb in (self.cb_content,self.cb_asst,self.cb_in_instruct,self.cb_out_instruct,self.cb_prompt_comp,self.cb_completion_comp):
            cb.configure(values=vals)
        self.cb_id.configure(values=["<None>"]+vals)
        guess = self._guess_content_col(self.headers)
        self.content_col.set(guess if guess else (vals[0] if vals else ""))
        self.id_col.set("<None>")
        self.status.set(f"Loaded {len(self.rows)} rows, {len(self.headers)} columns.")
        if not self.out_path.get() and self.mode.get()!="TXT → CSV (parse)":
            base = os.path.splitext(os.path.basename(path))[0]; self.out_path.set(f"{base}_batch.jsonl")

    def load_jsonl(self, path):
        """Load JSONL file and discover available fields"""
        try:
            records = self._read_jsonl_records(path)
            
            if not records:
                raise ValueError("No valid JSON records found.")
            
            # Discover all unique field paths
            self.jsonl_available_fields = self._discover_jsonl_fields(records)
            
            # Clear existing checkboxes
            for widget in self.jsonl_fields_frame.winfo_children():
                widget.destroy()
            
            # Create new checkboxes for each field
            self.jsonl_fields = {}
            for i, field_path in enumerate(self.jsonl_available_fields):
                var = tk.BooleanVar(value=True)  # Default to selected
                self.jsonl_fields[field_path] = var
                chk = ttk.Checkbutton(self.jsonl_fields_frame, text=field_path, variable=var, 
                                      command=self.refresh_preview)
                chk.grid(row=i, column=0, sticky="w", padx=6, pady=2)
            
            self.jsonl_path.set(path)
            self.jsonl_info_label.configure(text=f"{len(records)} records, {len(self.jsonl_available_fields)} fields")
            self.status.set(f"Loaded {len(records)} JSONL records.")
            
            if not self.out_path.get():
                base = os.path.splitext(os.path.basename(path))[0]
                self.out_path.set(f"{base}_export.csv")
                
        except Exception as e:
            messagebox.showerror("JSONL Error", f"Failed to read JSONL:\n{e}")
            self.jsonl_available_fields = []
            self.jsonl_fields = {}
            self.jsonl_info_label.configure(text="Open a JSONL file to see available fields")
            self.status.set("JSONL load failed.")

    def _read_jsonl_records(self, path, max_records=None):
        """Read JSONL records from file, optionally limiting the number of records"""
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line: continue
                try:
                    records.append(json.loads(line))
                    if max_records and len(records) >= max_records:
                        break
                except json.JSONDecodeError as e:
                    if line_num <= 100:  # Only warn for first 100 lines to avoid spam
                        messagebox.showwarning("Parse Warning", f"Line {line_num} is not valid JSON: {e}")
                    continue
        return records

    def _discover_jsonl_fields(self, records, max_depth=5):
        """Discover all unique field paths in JSONL records"""
        fields = set()
        
        def traverse(obj, path="", depth=0):
            if depth > max_depth:
                return

            # Attempt to parse JSON strings so we can discover nested fields even if
            # the batch response stored the HTTP body as text.
            if isinstance(obj, str):
                stripped = obj.strip()
                if stripped.startswith(("{", "[")):
                    try:
                        parsed = json.loads(stripped)
                    except Exception:
                        pass
                    else:
                        traverse(parsed, path, depth)
                if path:
                    fields.add(path)
                return

            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key

                    if isinstance(value, (dict, list)):
                        traverse(value, new_path, depth + 1)
                    elif isinstance(value, str):
                        stripped = value.strip()
                        if stripped.startswith(("{", "[")):
                            traverse(value, new_path, depth + 1)
                        if new_path:
                            fields.add(new_path)
                    else:
                        fields.add(new_path)
            elif isinstance(obj, list):
                # For lists, check the first few items to discover fields
                for i, item in enumerate(obj[:MAX_ARRAY_ITEMS_TO_CHECK]):
                    if isinstance(item, dict):
                        # For message arrays, include role-specific paths
                        traverse(item, f"{path}[{i}]", depth + 1)
                    elif isinstance(item, (list, str)):
                        if isinstance(item, str):
                            stripped = item.strip()
                            if stripped.startswith(("{", "[")):
                                traverse(item, f"{path}[{i}]", depth + 1)
                        else:
                            traverse(item, f"{path}[{i}]", depth + 1)
                        if path:
                            fields.add(path)
                        break
                    elif not isinstance(item, list):
                        # For simple lists, just note the array itself
                        fields.add(path)
                        break
        
        for record in records:
            traverse(record)
        
        # Sort fields with better ordering: top-level first, then nested
        def sort_key(field):
            depth = field.count('.')
            has_index = '[' in field
            return (depth, has_index, field)
        
        return sorted(fields, key=sort_key)

    def select_all_jsonl_fields(self):
        """Select all JSONL fields"""
        for var in self.jsonl_fields.values():
            var.set(True)
        self.refresh_preview()

    def deselect_all_jsonl_fields(self):
        """Deselect all JSONL fields"""
        for var in self.jsonl_fields.values():
            var.set(False)
        self.refresh_preview()

    # ----- build -----
    def build_output(self):
        mode = self.mode.get()
        out_path = self._ensure_out_path()
        if not out_path: return
        try:
            if mode in ("TXT → CSV (parse)", "JSONL → CSV (de-JSONL)"):
                if mode == "TXT → CSV (parse)":
                    recs = self._parse_txt_records()
                    delimiter = self.csv_delimiter.get() or ","
                    title_header = self.custom_title_header.get() or "title"
                    content_header = self.custom_content_header.get() or "content"
                    with open(out_path, "w", encoding="utf-8", newline="") as fh:
                        w = csv.writer(fh, delimiter=delimiter)
                        w.writerow([title_header, content_header])
                        for r in recs: w.writerow([r["title"], r["content"]])
                    count = len(recs)
                else:  # JSONL → CSV (de-JSONL)
                    count = self._build_jsonl_to_csv(out_path)
                size = Path(out_path).stat().st_size
            else:
                with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
                    if mode == "Batch Inference (CSV)":
                        count, size = self._build_batch_inference_csv(fh)
                    elif mode == "Finetune: Chat":
                        count, size = self._build_finetune_chat(fh)
                    elif mode == "Finetune: Instruct":
                        count, size = self._build_finetune_instruct(fh)
                    elif mode == "Finetune: Completions":
                        count, size = self._build_finetune_completions(fh)
                    else:
                        count, size = self._build_docs_batch(fh)
        except Exception as e:
            messagebox.showerror("Write Error", f"Failed to write output:\n{e}")
            self.status.set("Build failed."); return

        suffix = Path(out_path).suffix.lower()
        if suffix == ".jsonl":
            size_mb = size / (1024*1024)
            if size_mb > 500:
                messagebox.showwarning("Size Warning", f"Saved but exceeds 500MB: {size_mb:.1f} MB")
            else:
                messagebox.showinfo("Done", f"Wrote {count} lines\n{out_path}\nSize: {size_mb:.1f} MB")
        else:
            messagebox.showinfo("Done", f"Wrote {count} rows\n{out_path}")
        self.status.set(f"Finished: {count} → {os.path.basename(out_path)}")

    def _ensure_out_path(self):
        out_path = self.out_path.get().strip()
        if not out_path:
            self.menu_save_output(); out_path = self.out_path.get().strip()
            if not out_path: return None
        if Path(out_path).suffix == "":
            if self.mode.get() in ("TXT → CSV (parse)", "JSONL → CSV (de-JSONL)"):
                out_path += ".csv"
            else:
                out_path += ".jsonl"
            self.out_path.set(out_path)
        return out_path

    # ----- builders for JSONL modes -----
    def _build_batch_inference_csv(self, fh):
        if not self.rows or not self.headers: raise ValueError("Load a CSV first.")
        content_col = self.content_col.get().strip()
        if content_col not in self.headers: raise ValueError(f"Content column not found: {content_col}")
        id_choice = self.id_col.get().strip()
        use_id_col = id_choice and id_choice!="<None>" and id_choice in self.headers
        system_prompt = self.txt_prompt.get("1.0","end").strip()
        seen, prefix = set(), (self.prefix_id.get().strip() or DEFAULT_PREFIX)
        written=size_bytes=0
        for idx,row in enumerate(self.rows, start=1):
            content = (row.get(content_col) or "").strip()
            if not content: continue
            msgs=[]
            if system_prompt: msgs.append({"role":"system","content":system_prompt})
            msgs.append({"role":"user","content":content})
            cid = (str(row.get(id_choice,"")).strip() if use_id_col else f"{prefix}{idx}") or f"{prefix}{idx}"
            base, bump = cid, 1
            while cid in seen: bump+=1; cid=f"{base}-{bump}"
            seen.add(cid)
            body = {"messages": msgs}
            if self.include_params.get():
                body["max_tokens"] = self.max_tokens.get()
                body["temperature"] = self.temperature.get()
            obj={"custom_id":cid,"body":body}
            line=json.dumps(obj, ensure_ascii=False); fh.write(line+"\n")
            written+=1; size_bytes+=len((line+"\n").encode("utf-8"))
        return written, size_bytes

    def _build_finetune_chat(self, fh):
        if not self.rows or not self.headers: raise ValueError("Load a CSV first.")
        ucol = self.content_col.get().strip(); acol = self.assistant_col.get().strip()
        if ucol not in self.headers or acol not in self.headers: raise ValueError("Specify valid user and assistant columns.")
        system_prompt = self.txt_prompt.get("1.0","end").strip()
        written=size_bytes=0
        for row in self.rows:
            u=(row.get(ucol) or "").strip(); a=(row.get(acol) or "").strip()
            if not u or not a: continue
            msgs=[]
            if system_prompt: msgs.append({"role":"system","content":system_prompt})
            msgs.append({"role":"user","content":u}); msgs.append({"role":"assistant","content":a})
            line=json.dumps({"messages":msgs}, ensure_ascii=False); fh.write(line+"\n")
            written+=1; size_bytes+=len((line+"\n").encode("utf-8"))
        return written, size_bytes

    def _build_finetune_instruct(self, fh):
        if not self.rows or not self.headers: raise ValueError("Load a CSV first.")
        ic=self.instruct_in_col.get().strip(); oc=self.instruct_out_col.get().strip()
        if ic not in self.headers or oc not in self.headers: raise ValueError("Specify valid input and output columns.")
        written=size_bytes=0
        for row in self.rows:
            i=(row.get(ic) or "").strip(); o=(row.get(oc) or "").strip()
            if not i or not o: continue
            line=json.dumps({"input":i,"output":o}, ensure_ascii=False); fh.write(line+"\n")
            written+=1; size_bytes+=len((line+"\n").encode("utf-8"))
        return written, size_bytes

    def _build_finetune_completions(self, fh):
        if not self.rows or not self.headers: raise ValueError("Load a CSV first.")
        pc=self.comp_prompt_col.get().strip(); cc=self.comp_completion_col.get().strip()
        if pc not in self.headers or cc not in self.headers: raise ValueError("Specify valid prompt and completion columns.")
        written=size_bytes=0
        for row in self.rows:
            p=(row.get(pc) or "").strip(); c=(row.get(cc) or "").strip()
            if not p or not c: continue
            line=json.dumps({"prompt":p,"completion":c}, ensure_ascii=False); fh.write(line+"\n")
            written+=1; size_bytes+=len((line+"\n").encode("utf-8"))
        return written, size_bytes

    def _build_docs_batch(self, fh):
        root = self.docs_dir.get().strip()
        if not root: raise ValueError("Select a documents folder.")
        system_prompt = self.txt_prompt.get("1.0","end").strip()
        suffixes=set(SUPPORTED_SUFFIXES)
        extra=[s.strip() for s in self.suffix_extra.get().split(",") if s.strip()]
        for s in extra:
            sfx = s if s.startswith(".") else "."+s
            suffixes.add(sfx.lower())
        files = iter_text_files(Path(root), suffixes)
        if not files: raise ValueError("No supported files found under the folder.")
        written=size_bytes=0; i=0
        for fp in files:
            text = read_document(Path(fp), enable_ocr=self.ocr_enabled.get(), ocr_language=self.ocr_lang.get(), ocr_dpi=self.ocr_dpi.get())
            if not text.strip(): continue
            parts = chunk_sentence_safe(text, target_words=self.target_words.get(),
                                        overlap_sents=self.overlap_sents.get(),
                                        by_paragraph_only=self.para_only.get())
            for j,t in enumerate(parts):
                i += 1
                msgs=[]
                if system_prompt: msgs.append({"role":"system","content":system_prompt})
                user_msg = (
                    "Using only the context below, provide a concise answer to this request: "
                    "'Summarize key facts and terms clearly'. If information is missing, say you don't know.\n\n"
                    f"Context (source: {Path(fp).name}, chunk {j}):\n{t}"
                )
                msgs.append({"role":"user","content":user_msg})
                obj={"custom_id":f"{DEFAULT_PREFIX}{i}","body":{"messages":msgs}}
                line=json.dumps(obj, ensure_ascii=False); fh.write(line+"\n")
                written+=1; size_bytes+=len((line+"\n").encode("utf-8"))
        if written==0: raise ValueError("No chunks produced from documents.")
        return written, size_bytes

    def _build_jsonl_to_csv(self, out_path):
        """Convert JSONL to CSV with selected fields"""
        jsonl_file = self.jsonl_path.get().strip()
        if not jsonl_file:
            raise ValueError("Select a JSONL file first.")
        
        # Get selected fields
        selected_fields = [field for field, var in self.jsonl_fields.items() if var.get()]
        if not selected_fields:
            raise ValueError("Select at least one field to export.")
        
        # Read JSONL records
        records = self._read_jsonl_records(jsonl_file)
        
        if not records:
            raise ValueError("No valid records in JSONL file.")
        
        # Extract field values for each record
        rows = []
        for record in records:
            row = {}
            for field_path in selected_fields:
                value = self._extract_field_value(record, field_path)
                row[field_path] = value
            rows.append(row)
        
        # Write CSV
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=selected_fields)
            writer.writeheader()
            writer.writerows(rows)
        
        return len(rows)

    def _extract_field_value(self, obj, path):
        """Extract value from nested object using dot notation path"""
        if not path:
            return ""
        
        parts = path.split(".")
        current = obj
        
        for idx, part in enumerate(parts):
            if current is None:
                return ""
            
            # Handle array indexing like "messages[0]"
            try:
                # If we still have more path components and the current value is a
                # JSON string, try to decode it so that nested lookups work even
                # when the batch API stored the body as text.
                if isinstance(current, str) and part and idx < len(parts) - 1:
                    stripped = current.strip()
                    if stripped.startswith(("{", "[")):
                        try:
                            current = json.loads(stripped)
                        except Exception:
                            return ""

                key_part = part
                indexes = []

                if "[" in part:
                    key_part = part[:part.index("[")]
                    rest = part[len(key_part):]
                    while rest.startswith("["):
                        close = rest.find("]")
                        if close == -1:
                            return ""
                        indexes.append(rest[1:close])
                        rest = rest[close + 1:]
                    if rest:
                        return ""

                if key_part:
                    if not isinstance(current, dict):
                        return ""
                    if key_part not in current:
                        return ""
                    current = current[key_part]

                for index_str in indexes:
                    try:
                        index = int(index_str)
                    except ValueError:
                        return ""
                    if not isinstance(current, list):
                        return ""
                    if not (0 <= index < len(current)):
                        return ""
                    current = current[index]
            except Exception:
                return ""

        # Convert to string representation
        if current is None:
            return ""
        elif isinstance(current, (dict, list)):
            return json.dumps(current, ensure_ascii=False)
        else:
            return str(current)

    # ----- preview -----
    def refresh_preview(self):
        prefix = self._make_common_prefix_preview()
        self.prefix_box.configure(state="normal"); self.prefix_box.delete("1.0","end"); self.prefix_box.insert("1.0", prefix); self.prefix_box.configure(state="disabled")
        uniq = self._make_unique_preview()
        self.preview_box.configure(state="normal"); self.preview_box.delete("1.0","end")
        self.preview_box.insert("1.0", uniq if uniq else "(no preview)"); self.preview_box.configure(state="disabled")

    def _make_common_prefix_preview(self) -> str:
        mode = self.mode.get()
        if mode == "TXT → CSV (parse)":
            delimiter = self.csv_delimiter.get() or ","
            title_h = self.custom_title_header.get() or "title"
            content_h = self.custom_content_header.get() or "content"
            delim_name = {"\\t": "tab", ",": "comma", ";": "semicolon", "|": "pipe"}.get(delimiter, delimiter)
            info = f"CSV output with {delim_name} delimiter\nColumns: {title_h}, {content_h}"
            if self.use_line_range.get():
                info += f"\nParsing lines {self.start_line.get()} to {self.end_line.get() if self.end_line.get() > 0 else 'end'}"
            if self.has_header_row.get():
                info += "\nSkipping first row as header"
            return info
        if mode == "JSONL → CSV (de-JSONL)":
            selected_fields = [field for field, var in self.jsonl_fields.items() if var.get()]
            if selected_fields:
                fields_str = "\n  ".join(selected_fields)
                return f"CSV Export - Selected Fields:\n  {fields_str}"
            else:
                return "CSV Export - No fields selected"
        sys_prompt = self.txt_prompt.get("1.0","end").strip()
        if mode in ("Batch Inference (CSV)", "Docs → Batch Inference"):
            if mode == "Batch Inference (CSV)" and self.include_params.get():
                return (
                    '{ "custom_id": "request-N", "body": { '
                    f'"max_tokens": {self.max_tokens.get()}, '
                    f'"temperature": {self.temperature.get()}, '
                    '"messages": [\n'
                    f'  {{"role": "system", "content": "{sys_prompt}"}},\n'
                    '  {"role": "user", "content": "...content..."}\n]} }'
                )
            else:
                return (
                    '{ "custom_id": "request-N", "body": { "messages": [\n'
                    f'  {{"role": "system", "content": "{sys_prompt}"}},\n'
                    '  {"role": "user", "content": "Using only the context below, provide a concise answer to this request:'
                    " 'Summarize key facts and terms clearly'. If information is missing, say you don't know.\\n\\n"
                    'Context (source: <file>, chunk <i>):\\n...CHUNK TEXT HERE..."}\n]} }'
                )
        if mode == "Finetune: Chat":
            return (
                '{ "messages": [\n'
                f'  {{"role": "system", "content": "{sys_prompt}"}},\n'
                '  {"role": "user", "content": "<user>"},\n'
                '  {"role": "assistant", "content": "<assistant>"}\n]}'
            )
        if mode == "Finetune: Instruct":
            return '{ "input": "<input>", "output": "<output>" }'
        return '{ "prompt": "<prompt>", "completion": "<completion>" }'

    def _make_unique_preview(self) -> str:
        try:
            mode = self.mode.get()
            if mode == "Batch Inference (CSV)":
                return self._prev_batch_csv()
            if mode == "Finetune: Chat":
                return self._prev_ft_chat()
            if mode == "Finetune: Instruct":
                return self._prev_ft_instruct()
            if mode == "Finetune: Completions":
                return self._prev_ft_compl()
            if mode == "Docs → Batch Inference":
                return self._prev_docs_batch()
            if mode == "JSONL → CSV (de-JSONL)":
                return self._prev_jsonl_to_csv()
            return self._prev_txt_csv()
        except Exception as e:
            return f"(preview error) {e}"

    def _prev_batch_csv(self):
        if not self.rows or not self.headers: return "Load a CSV to preview."
        col = self.content_col.get().strip()
        if col not in self.headers: return f"Content column not found: {col}"
        prefix = self.prefix_id.get().strip() or DEFAULT_PREFIX
        out=[]; n=0
        for i,row in enumerate(self.rows, start=1):
            content=(row.get(col) or "").strip()
            if not content: continue
            out.append(f"[{prefix}{i}] content:\n{content}\n---"); n+=1
            if n>=PREVIEW_LINES: break
        return "\n".join(out) if out else "(no non-empty rows)"

    def _prev_ft_chat(self):
        if not self.rows or not self.headers: return "Load a CSV to preview."
        ucol=self.content_col.get().strip(); acol=self.assistant_col.get().strip()
        if ucol not in self.headers or acol not in self.headers: return "Specify valid user and assistant columns."
        out=[]; n=0
        for r in self.rows:
            u=(r.get(ucol) or "").strip(); a=(r.get(acol) or "").strip()
            if not u or not a: continue
            out.append(f"user:\n{u}\nassistant:\n{a}\n---"); n+=1
            if n>=PREVIEW_LINES: break
        return "\n".join(out) if out else "(no valid rows)"

    def _prev_ft_instruct(self):
        if not self.rows or not self.headers: return "Load a CSV to preview."
        ic=self.instruct_in_col.get().strip(); oc=self.instruct_out_col.get().strip()
        if ic not in self.headers or oc not in self.headers: return "Specify valid input and output columns."
        out=[]; n=0
        for r in self.rows:
            i=(r.get(ic) or "").strip(); o=(r.get(oc) or "").strip()
            if not i or not o: continue
            out.append(f"input:\n{i}\noutput:\n{o}\n---"); n+=1
            if n>=PREVIEW_LINES: break
        return "\n".join(out) if out else "(no valid rows)"

    def _prev_ft_compl(self):
        if not self.rows or not self.headers: return "Load a CSV to preview."
        pc=self.comp_prompt_col.get().strip(); cc=self.comp_completion_col.get().strip()
        if pc not in self.headers or cc not in self.headers: return "Specify valid prompt/completion columns."
        out=[]; n=0
        for r in self.rows:
            p=(r.get(pc) or "").strip(); c=(r.get(cc) or "").strip()
            if not p or not c: continue
            out.append(f"prompt:\n{p}\ncompletion:\n{c}\n---"); n+=1
            if n>=PREVIEW_LINES: break
        return "\n".join(out) if out else "(no valid rows)"

    def _prev_docs_batch(self):
        root = self.docs_dir.get().strip()
        if not root: return "Choose a documents folder."
        suffixes=set(SUPPORTED_SUFFIXES)
        extra=[s.strip() for s in self.suffix_extra.get().split(",") if s.strip()]
        for s in extra:
            sfx = s if s.startswith(".") else "."+s
            suffixes.add(sfx.lower())
        files = iter_text_files(Path(root), suffixes)
        if not files: return "No supported files in folder."
        out=[]; n=0
        for fp in files:
            text = read_document(Path(fp), enable_ocr=self.ocr_enabled.get(), ocr_language=self.ocr_lang.get(), ocr_dpi=self.ocr_dpi.get())
            if not text.strip(): continue
            parts = chunk_sentence_safe(text, target_words=self.target_words.get(),
                                        overlap_sents=self.overlap_sents.get(),
                                        by_paragraph_only=self.para_only.get())
            for j,t in enumerate(parts):
                out.append(f"[{Path(fp).name} | chunk {j}]\n{t}\n---"); n+=1
                if n>=PREVIEW_LINES: return "\n".join(out)
        return "\n".join(out) if out else "(no chunks produced)"

    def _prev_txt_csv(self):
        if not self.txt_path.get(): return "Choose a TXT file."
        try:
            # Show raw text preview first (limited lines)
            p = Path(self.txt_path.get().strip())
            if not p.is_file():
                return "TXT file not found."
            
            try:
                full_txt = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                full_txt = p.read_text(encoding="latin-1", errors="ignore")
            
            lines = full_txt.split('\n')
            preview_info = f"Total lines in file: {len(lines)}\n"
            
            if self.use_line_range.get():
                start_idx = max(0, int(self.start_line.get()) - 1)
                end_idx = int(self.end_line.get())
                if end_idx < 0 or end_idx > len(lines):
                    end_idx = len(lines)
                preview_info += f"Parsing lines {start_idx + 1} to {end_idx}\n"
            
            preview_info += "\n=== Parsed Records Preview ===\n"
            
            recs = self._parse_txt_records()
            preview_info += f"Total parsed records: {len(recs)}\n\n"
            
            out = [preview_info]
            for i, r in enumerate(recs[:PREVIEW_LINES], 1):
                title = r["title"] or "(no title)"
                content_preview = r['content'][:200] + "..." if len(r['content']) > 200 else r['content']
                out.append(f"Record {i}:\n  Title: {title}\n  Content: {content_preview}\n---")
            return "\n".join(out) if len(out) > 1 else out[0] + "(no records)"
        except Exception as e:
            return f"(parse error) {e}"

    def _prev_jsonl_to_csv(self):
        """Preview JSONL to CSV conversion"""
        jsonl_file = self.jsonl_path.get().strip()
        if not jsonl_file:
            return "Choose a JSONL file."
        
        selected_fields = [field for field, var in self.jsonl_fields.items() if var.get()]
        if not selected_fields:
            return "Select at least one field to export."
        
        try:
            # Read first few records for preview
            records = self._read_jsonl_records(jsonl_file, max_records=PREVIEW_LINES)
            
            if not records:
                return "No valid records in JSONL file."
            
            # Build preview
            out = []
            for i, record in enumerate(records, 1):
                out.append(f"Record {i}:")
                for field_path in selected_fields:
                    value = self._extract_field_value(record, field_path)
                    # Truncate long values
                    if len(str(value)) > 100:
                        value = str(value)[:100] + "..."
                    out.append(f"  {field_path}: {value}")
                out.append("---")
            
            return "\n".join(out)
        except Exception as e:
            return f"(preview error) {e}"

    # ----- helpers -----
    def _parse_txt_records(self):
        p = Path(self.txt_path.get().strip())
        if not p.is_file():
            raise ValueError("TXT file not found.")
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            txt = p.read_text(encoding="latin-1", errors="ignore")
        
        # Handle section selection if enabled
        if self.use_line_range.get():
            lines = txt.split('\n')
            start_idx = max(0, int(self.start_line.get()) - 1)  # Convert to 0-indexed
            end_idx = int(self.end_line.get())
            if end_idx < 0 or end_idx > len(lines):
                end_idx = len(lines)
            lines = lines[start_idx:end_idx]
            txt = '\n'.join(lines)
        
        # Skip header row if enabled
        if self.has_header_row.get():
            lines = txt.split('\n')
            if lines:
                lines = lines[1:]  # Skip first line
                txt = '\n'.join(lines)
        
        cfg = {
            "min_line_len": max(0, int(self.min_line_len.get())),
            "detect_all_caps": bool(self.detect_all_caps.get()),
            "detect_title_case": bool(self.detect_title_case.get()),
            "detect_numbered": bool(self.detect_numbered.get()),
            "min_heading_chars": max(1, int(self.min_heading_chars.get())),
            "max_heading_chars": max(10, int(self.max_heading_chars.get())),
            "split_on_separators": bool(self.split_on_separators.get()),
            "min_separator_len": max(3, int(self.min_separator_len.get())),
        }
        return parse_txt_to_records(txt, cfg)

    @staticmethod
    def _guess_content_col(headers):
        candidates = ["text","prompt","content","query","question","input","user","instruction"]
        low = {h.lower(): h for h in headers}
        for c in candidates:
            if c in low: return low[c]
        return None

if __name__ == "__main__":
    app = App(); app.mainloop()
