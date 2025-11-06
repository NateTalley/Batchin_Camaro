#!/usr/bin/env python3
# Dataset JSONL Builder + Escape Sequence Decoder
# Features:
# - Batch inference from CSV
# - Fine-tuning data generation (Chat, Instruct, Completions)
# - Document chunking for RAG
# - Escape sequence decoding (\n, \t, etc.)

import csv, json, os, re, sys, codecs
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

# Optional: pandas for JSON → Finetune mode
try:
    import pandas as pd
except ImportError:
    pd = None

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

MODES = [
    "Batch Inference (CSV)",
    "Finetune: Chat",
    "Finetune: Instruct",
    "Finetune: Completions",
    "Docs → Batch Inference",
    "JSON → Finetune",
    "Decode Escape Sequences",
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
    "JSON → Finetune": "You are a helpful assistant.",
    "Decode Escape Sequences": "",
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

# ------------------ Escape sequence decoding ------------------
def decode_escape_sequences(text: str) -> str:
    """
    Decode common escape sequences in text to their readable format.
    Primary method handles: \\n, \\t, \\r, \\\\, \\', \\", \\x__ (hex), \\u____ (unicode), etc.
    Fallback method handles: \\n, \\t, \\r, \\\\, \\', \\"
    """
    # Use Python's built-in decode with 'unicode_escape' for most sequences
    try:
        # Decode unicode escape sequences
        decoded = codecs.decode(text, 'unicode_escape')
        # If input was str, decode will return bytes, so decode back to str
        if isinstance(decoded, bytes):
            decoded = decoded.decode('utf-8')
        return decoded
    except (UnicodeDecodeError, ValueError):
        # Fallback: manual replacement with correct order
        # Note: This fallback only handles basic sequences, not hex or unicode
        result = text
        # Replace double backslashes first to preserve literal backslashes
        result = result.replace('\\\\', '\x00')  # Temporary placeholder
        result = result.replace('\\n', '\n')
        result = result.replace('\\t', '\t')
        result = result.replace('\\r', '\r')
        result = result.replace("\\'", "'")
        result = result.replace('\\"', '"')
        result = result.replace('\x00', '\\')  # Replace placeholder with single backslash
        return result

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

        # Escape sequence decoding
        self.escape_input_path = tk.StringVar()
        self.escape_output_path = tk.StringVar()
        
        # JSON → Finetune
        self.batch_input_path = tk.StringVar()
        self.batch_output_path = tk.StringVar()

        # Menu
        mbar = tk.Menu(self)
        filem = tk.Menu(mbar, tearoff=0)
        filem.add_command(label="Open CSV…", command=self.menu_open_csv)
        filem.add_command(label="Open Input File…", command=self.menu_open_escape_input)
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
        # Escape input
        self.lbl_escape_input = ttk.Label(fr_paths, text="Input file:")
        self.ent_escape_input = ttk.Entry(fr_paths, textvariable=self.escape_input_path)
        self.btn_escape_input = ttk.Button(fr_paths, text="Open…", command=self.menu_open_escape_input, width=12)
        # Batch input (JSON → Finetune)
        self.lbl_batch_input = ttk.Label(fr_paths, text="Batch output file:")
        self.ent_batch_input = ttk.Entry(fr_paths, textvariable=self.batch_input_path)
        self.btn_batch_input = ttk.Button(fr_paths, text="Open…", command=self.menu_open_batch_input, width=12)

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

        # Escape sequence decoding settings
        fr_escape = ttk.LabelFrame(left, text="Escape Sequence Decoding")
        fr_escape.pack(fill="x", padx=10, pady=8)
        ttk.Label(fr_escape, text="Decodes escape sequences like \\n, \\t, \\r, \\\\, etc. into readable format").pack(padx=6, pady=6, anchor="w")

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
                  self.lbl_escape_input, self.ent_escape_input, self.btn_escape_input,
                  self.lbl_batch_input, self.ent_batch_input, self.btn_batch_input):
            try: w.grid_forget()
            except Exception: pass

        mode = self.mode.get()
        if mode == "Docs → Batch Inference":
            self.lbl_docs.grid(row=0, column=0, sticky="w", padx=6, pady=6)
            self.ent_docs.grid(row=0, column=1, sticky="we", padx=6, pady=6)
            self.btn_docs.grid(row=0, column=2, padx=6, pady=6)
        elif mode == "Decode Escape Sequences":
            self.lbl_escape_input.grid(row=0, column=0, sticky="w", padx=6, pady=6)
            self.ent_escape_input.grid(row=0, column=1, sticky="we", padx=6, pady=6)
            self.btn_escape_input.grid(row=0, column=2, padx=6, pady=6)
        elif mode == "JSON → Finetune":
            self.lbl_batch_input.grid(row=0, column=0, sticky="w", padx=6, pady=6)
            self.ent_batch_input.grid(row=0, column=1, sticky="we", padx=6, pady=6)
            self.btn_batch_input.grid(row=0, column=2, padx=6, pady=6)
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
        self._set_group_state("Escape Sequence Decoding", "normal" if mode=="Decode Escape Sequences" else "disabled")

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

    def menu_open_escape_input(self):
        path = filedialog.askopenfilename(title="Select Input File", filetypes=[("Text files","*.txt"),("All files","*.*")])
        if not path: return
        self.escape_input_path.set(path); self.refresh_preview()

    def menu_open_batch_input(self):
        path = filedialog.askopenfilename(title="Select Batch Output JSONL", filetypes=[("JSONL files","*.jsonl"),("All files","*.*")])
        if not path: return
        self.batch_input_path.set(path); self.refresh_preview()

    def menu_save_output(self):
        mode = self.mode.get()
        if mode == "Decode Escape Sequences":
            ftypes = [("Text files","*.txt"),("All files","*.*")]
            dflt = ".txt"
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
        if not self.out_path.get() and self.mode.get() != "Decode Escape Sequences":
            base = os.path.splitext(os.path.basename(path))[0]; self.out_path.set(f"{base}_batch.jsonl")

    # ----- build -----
    def build_output(self):
        mode = self.mode.get()
        out_path = self._ensure_out_path()
        if not out_path: return
        try:
            if mode == "Decode Escape Sequences":
                self._build_escape_decode(out_path)
                files_processed = 1; size = Path(out_path).stat().st_size
                count = files_processed  # For consistency with other modes
            elif mode == "JSON → Finetune":
                count, size = self._build_json_to_finetune(out_path)
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
            messagebox.showinfo("Done", f"Wrote output to:\n{out_path}")
        self.status.set(f"Finished: {count} → {os.path.basename(out_path)}")

    def _ensure_out_path(self):
        out_path = self.out_path.get().strip()
        if not out_path:
            self.menu_save_output(); out_path = self.out_path.get().strip()
            if not out_path: return None
        if Path(out_path).suffix == "":
            if self.mode.get()=="Decode Escape Sequences":
                out_path += ".txt"
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

    def _build_escape_decode(self, out_path):
        """Decode escape sequences from input file and write to output."""
        input_path = self.escape_input_path.get().strip()
        if not input_path: raise ValueError("Select an input file.")
        p = Path(input_path)
        if not p.is_file(): raise ValueError("Input file not found.")
        
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = p.read_text(encoding="latin-1", errors="ignore")
        
        decoded = decode_escape_sequences(text)
        
        Path(out_path).write_text(decoded, encoding="utf-8")

    def _build_json_to_finetune(self, out_path):
        """
        Convert batch output JSONL to fine-tuning chat format.
        Reads a batch output JSONL file, parses the model's JSON response,
        and writes a new "Finetune: Chat" JSONL file.
        """
        input_path = self.batch_input_path.get().strip()
        if not input_path: raise ValueError("Select a batch output file.")
        
        input_file = Path(input_path)
        if not input_file.is_file(): raise ValueError("Batch output file not found.")
        
        system_prompt = self.txt_prompt.get("1.0", "end").strip()
        
        # Use pandas to read the batch output JSONL as per HBIC.md instructions
        if pd is None:
            raise ValueError("pandas is required for JSON → Finetune mode. Install dependencies from requirements.txt")
        
        try:
            df = pd.read_json(input_path, lines=True)
        except Exception as e:
            raise ValueError(f"Could not read input file '{input_path}'. Details: {e}\nPlease make sure the file exists and is a valid JSONL.")
        
        generated_chats = []
        
        # Iterate over each row from the batch output
        for index, row in df.iterrows():
            try:
                # Extract the model's response content
                # Supports multiple formats:
                # 1. OpenAI Batch API format: body.choices[0].message.content
                # 2. Generic response format: response.content
                # 3. Nested message format: response.message.content
                # Add additional format handlers below as needed for other providers
                model_content = None
                
                if 'body' in row and isinstance(row['body'], dict) and 'choices' in row['body']:
                    choices = row['body']['choices']
                    if isinstance(choices, list) and len(choices) > 0 and 'message' in choices[0]:
                        model_content = choices[0]['message'].get('content')
                # Add other common formats as needed
                elif 'response' in row and isinstance(row['response'], dict):
                    if 'content' in row['response']:
                        model_content = row['response']['content']
                    elif 'message' in row['response'] and isinstance(row['response']['message'], dict):
                        model_content = row['response']['message'].get('content')
                
                if model_content is None:
                    # Silently skip rows with unexpected formats
                    continue
                
                # The model content itself is a JSON string. Parse it.
                qa_pair = json.loads(model_content)
                
                if 'question' not in qa_pair or 'answer' not in qa_pair:
                    # Silently skip rows missing required keys
                    continue
                
                # Format as a chat message list
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                
                messages.append({"role": "user", "content": qa_pair['question']})
                messages.append({"role": "assistant", "content": qa_pair['answer']})
                
                generated_chats.append({"messages": messages})
            
            except json.JSONDecodeError:
                # Silently skip rows with invalid JSON in model content
                pass
            except Exception:
                # Silently skip rows with other errors
                pass
        
        # Save the final chat data
        if not generated_chats:
            raise ValueError("No valid chat data was generated from the batch output.")
        
        # Use standard library to write the final JSONL
        written = 0
        size_bytes = 0
        with open(out_path, 'w', encoding='utf-8') as f:
            for chat in generated_chats:
                line = json.dumps(chat, ensure_ascii=False)
                f.write(line + '\n')
                written += 1
                size_bytes += len((line + '\n').encode('utf-8'))
        
        print(f"\nDone! Successfully converted {written} items.")
        print(f"Final fine-tuning file is ready: {out_path}")
        
        return written, size_bytes

    # ----- preview -----
    def refresh_preview(self):
        prefix = self._make_common_prefix_preview()
        self.prefix_box.configure(state="normal"); self.prefix_box.delete("1.0","end"); self.prefix_box.insert("1.0", prefix); self.prefix_box.configure(state="disabled")
        uniq = self._make_unique_preview()
        self.preview_box.configure(state="normal"); self.preview_box.delete("1.0","end")
        self.preview_box.insert("1.0", uniq if uniq else "(no preview)"); self.preview_box.configure(state="disabled")

    def _make_common_prefix_preview(self) -> str:
        mode = self.mode.get()
        if mode == "Decode Escape Sequences":
            return "Decodes escape sequences (\\n → newline, \\t → tab, etc.)\nInput file will be decoded and saved to output."
        if mode == "JSON → Finetune":
            sys_prompt = self.txt_prompt.get("1.0","end").strip()
            return (
                'Converts batch output JSONL to fine-tuning chat format.\n\n'
                'Expected input format (batch output):\n'
                '{ "body": { "choices": [{ "message": { "content": "{\\"question\\": \\"..\\", \\"answer\\": \\"..\\"}" }}]}}\n\n'
                'Output format (fine-tuning chat):\n'
                '{ "messages": [\n'
                f'  {{"role": "system", "content": "{sys_prompt}"}},\n'
                '  {"role": "user", "content": "<question>"},\n'
                '  {"role": "assistant", "content": "<answer>"}\n]}'
            )
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
            if mode == "JSON → Finetune":
                return self._prev_json_to_finetune()
            return self._prev_escape_decode()
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

    def _prev_escape_decode(self):
        input_path = self.escape_input_path.get().strip()
        if not input_path: return "Choose an input file."
        try:
            p = Path(input_path)
            if not p.is_file(): return "Input file not found."
            
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = p.read_text(encoding="latin-1", errors="ignore")
            
            # Only decode the preview portion for efficiency
            lines = text.split('\n')[:PREVIEW_LINES]
            original_preview = '\n'.join(lines)
            
            # Decode only the preview portion
            decoded = decode_escape_sequences(original_preview)
            decoded_preview = decoded
            
            return (f"=== Original (with escape sequences) ===\n{original_preview}\n\n"
                   f"=== Decoded (readable format) ===\n{decoded_preview}")
        except Exception as e:
            return f"(preview error) {e}"

    def _prev_json_to_finetune(self):
        input_path = self.batch_input_path.get().strip()
        if not input_path: return "Choose a batch output file."
        
        if pd is None:
            return "pandas is required for JSON → Finetune mode. Install dependencies from requirements.txt"
        
        try:
            p = Path(input_path)
            if not p.is_file(): return "Batch output file not found."
            
            # Read the batch output JSONL
            df = pd.read_json(input_path, lines=True)
            
            out = []
            n = 0
            system_prompt = self.txt_prompt.get("1.0", "end").strip()
            
            # Preview first few valid conversions
            for index, row in df.iterrows():
                try:
                    # Extract the model's response content
                    model_content = None
                    
                    if 'body' in row and isinstance(row['body'], dict) and 'choices' in row['body']:
                        choices = row['body']['choices']
                        if isinstance(choices, list) and len(choices) > 0 and 'message' in choices[0]:
                            model_content = choices[0]['message'].get('content')
                    elif 'response' in row and isinstance(row['response'], dict):
                        if 'content' in row['response']:
                            model_content = row['response']['content']
                        elif 'message' in row['response'] and isinstance(row['response']['message'], dict):
                            model_content = row['response']['message'].get('content')
                    
                    if model_content is None:
                        continue
                    
                    # Parse the model content as JSON
                    qa_pair = json.loads(model_content)
                    
                    if 'question' not in qa_pair or 'answer' not in qa_pair:
                        continue
                    
                    # Format preview
                    question = qa_pair['question'][:200] + ("..." if len(qa_pair['question']) > 200 else "")
                    answer = qa_pair['answer'][:200] + ("..." if len(qa_pair['answer']) > 200 else "")
                    
                    out.append(f"[Item {n+1}]\nQuestion: {question}\nAnswer: {answer}\n---")
                    n += 1
                    
                    if n >= PREVIEW_LINES:
                        break
                
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
            
            if not out:
                return "(no valid Q&A pairs found in batch output)"
            
            return "\n".join(out)
        
        except Exception as e:
            return f"(preview error) {e}"

    # ----- helpers -----
    @staticmethod
    def _guess_content_col(headers):
        candidates = ["text","prompt","content","query","question","input","user","instruction"]
        low = {h.lower(): h for h in headers}
        for c in candidates:
            if c in low: return low[c]
        return None

if __name__ == "__main__":
    app = App(); app.mainloop()
