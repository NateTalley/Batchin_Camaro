/** Internet Archive API helpers — search, metadata, file filtering. */

const TEXT_PDF_FORMATS = new Set([
  "Text PDF", "PDF with Text", "PDF WITH TEXT", "Additional Text PDF"
]);
const EXTRA_FORMATS = new Set([
  "JPEG", "JPEG Thumb", "JP2", "JP2 ZIP",
  "Single Page Processed JP2 ZIP", "Animated GIF", "PNG", "TIFF",
  "EPUB", "DAISY", "Kindle", "Word Document", "Microsoft Word"
]);

function isTextFile(f) {
  const name = (f.name || "").toLowerCase();
  return name.endsWith(".txt");
}

function isPdfFile(f) {
  const fmt = f.format || "";
  if (TEXT_PDF_FORMATS.has(fmt)) return true;
  const fl = fmt.toLowerCase();
  return fl.includes("text") && fl.includes("pdf");
}

function isExtraFile(f) {
  const fmt = f.format || "";
  if (EXTRA_FORMATS.has(fmt)) return true;
  const fl = fmt.toLowerCase();
  return fl.includes("jpeg") || fl.includes("jp2") || fl.includes("epub") || fl.includes("daisy");
}

async function searchItems(query, opts = {}) {
  const mediatype = opts.mediatype ?? null;
  const rows = opts.rows ?? 20;
  const page = opts.page ?? 1;
  let q = query.trim();
  if (!q) return [];
  if (mediatype) q = `(${q}) AND mediatype:${mediatype}`;

  const params = new URLSearchParams();
  params.set("q", q);
  params.append("fl[]", "identifier");
  params.append("fl[]", "title");
  params.append("fl[]", "mediatype");
  params.set("rows", String(Math.max(1, Math.min(rows, 100))));
  params.set("page", String(Math.max(1, page)));
  params.set("output", "json");

  const resp = await fetch(`https://archive.org/advancedsearch.php?${params}`);
  if (!resp.ok) throw new Error(`Search HTTP ${resp.status}`);
  const data = await resp.json();
  const docs = data?.response?.docs || [];

  return docs.map(doc => {
    let title = doc.title ?? doc.identifier ?? "";
    if (Array.isArray(title)) title = title[0] || doc.identifier;
    let mt = doc.mediatype ?? "";
    if (Array.isArray(mt)) mt = mt[0] || "";
    return { identifier: doc.identifier, title: String(title), mediatype: String(mt) };
  }).filter(d => d.identifier);
}

async function getMetadata(itemId) {
  const resp = await fetch(`https://archive.org/metadata/${encodeURIComponent(itemId)}`);
  if (!resp.ok) throw new Error(`Metadata HTTP ${resp.status}`);
  return resp.json();
}

function filterDownloadableFiles(metadata, opts = {}) {
  const wantText = opts.wantText !== false;
  const wantPdf = opts.wantPdf !== false;
  const wantExtra = opts.wantExtra === true;
  const files = metadata.files || [];
  return files.filter(f => {
    if (wantText && isTextFile(f)) return true;
    if (wantPdf && isPdfFile(f)) return true;
    if (wantExtra && isExtraFile(f)) return true;
    return false;
  });
}

function isRestricted(metadata) {
  if (metadata.is_dark === true) return true;
  const meta = metadata.metadata || {};
  return meta["access-restricted-item"] === "true";
}

function summarizeMetadata(metadata, opts = {}) {
  const wantText = opts.wantText !== false;
  const wantPdf = opts.wantPdf !== false;
  const files = filterDownloadableFiles(metadata, { wantText, wantPdf });
  const meta = metadata.metadata || {};
  let title = meta.title ?? metadata.identifier ?? "";
  if (Array.isArray(title)) title = title[0] || "";
  return {
    identifier: metadata.identifier || meta.identifier || "",
    title: String(title),
    restricted: isRestricted(metadata),
    file_count: files.length,
    files: files.slice(0, 30).map(f => ({ name: f.name, format: f.format, size: f.size }))
  };
}
