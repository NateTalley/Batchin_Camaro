# Multi-URL Quick Start Guide

## What's New?

You can now paste multiple archive.org URLs directly into Batchin' Camaro to batch download OCR-processed text and searchable PDFs!

## Quick Steps

1. **Select Mode**: Choose "Internet Archive Download" from the dropdown

2. **Enable Multi-URL Input**: Check the box "Use multi-line URL input"

3. **Paste Your URLs**: A text area appears. Paste your archive.org URLs, one per line:
   ```
   https://archive.org/details/item1
   https://archive.org/details/item2
   https://archive.org/details/item3
   ```

4. **Choose Format**: Select what to download:
   - **OCR Text**: Text files with OCR-extracted content (smaller, faster)
   - **PDF with Text**: Searchable PDFs (preserves layout, larger)
   - **Both**: Get everything

5. **Select Output**: Click "Browse..." to choose where files should be saved

6. **Click Run**: Downloads will start automatically!

## What Gets Downloaded?

Unlike generic downloads, this tool specifically targets **searchable, parseable content**:

### OCR Text
- Files marked as "OCR Search Text"
- Text files from OCR processing
- ABBYY FineReader output
- DjVu text layers

### PDF with Text  
- PDFs marked as "Text PDF" or "PDF WITH TEXT"
- Searchable PDFs where you can select/copy text
- NOT image-only PDFs

## Example Use Case

**Research Project**: Download OCR text from 10 historical books

**Before (Old Way)**:
- Open browser, find each book
- Download each file manually
- 10 clicks, 10 separate downloads
- Files scattered in Downloads folder

**Now (New Way)**:
1. Copy 10 URLs from your spreadsheet/notes
2. Paste into Batchin' Camaro
3. Click Run
4. All files organized in subdirectories

**Time saved**: ~5-10 minutes per batch!

## Tips & Tricks

### Use Comments
```
# Historical novels collection
https://archive.org/details/book1
https://archive.org/details/book2

# Scientific papers
https://archive.org/details/paper1
```

### Save Your URL List
Keep a text file with your URLs for future runs:
```
my_archive_urls.txt
```

### URL Formats Supported
All of these work:
```
https://archive.org/details/ItemID
http://archive.org/details/ItemID  
archive.org/details/ItemID
www.archive.org/details/ItemID
ItemID
```

### Organize with Subdirectories
Check "Create subdirectory for each item" to get:
```
output/
├── item1/
│   ├── item1_text.txt
│   └── item1_searchable.pdf
├── item2/
│   ├── item2_text.txt
│   └── item2_searchable.pdf
```

## Common Questions

**Q: Can I use this for command-line/automated workflows?**  
A: The GUI now has multi-URL input. For CLI automation, you might want to use the `internetarchive` Python library directly or create a simple script.

**Q: Why does it only download OCR/searchable files?**  
A: This tool is designed for text analysis and research. OCR text and searchable PDFs are the most useful formats for these purposes.

**Q: Can I mix URLs and item IDs?**  
A: Yes! You can paste full URLs, short URLs, or just item IDs on different lines.

**Q: What if a file doesn't exist for an item?**  
A: The tool will skip that item and continue with the rest.

## See Also

- `INTERNET_ARCHIVE_GUIDE.md` - Complete documentation
- `CSV_DOWNLOADER_GUIDE.md` - CSV-based bulk downloads
- `IMPLEMENTATION_SUMMARY.md` - Technical details

## Quick Reference

| Option | Purpose |
|--------|---------|
| **Use multi-line URL input** | Enable multi-URL mode |
| **OCR Text** | Download text files from OCR |
| **PDF with Text** | Download searchable PDFs |
| **Both** | Get all searchable content |
| **Create subdirectory for each item** | Organize by item |
| **Parse HTML in .txt files** | Clean up HTML-formatted text |
| **Delay** | Seconds between downloads (1-2 recommended) |

---

**Ready to start?** Just paste your URLs and click Run! 🏎️
