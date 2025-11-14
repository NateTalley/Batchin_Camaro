# Internet Archive Download Mode

This guide explains how to use the Internet Archive Download mode in Batchin' Camaro.

## Overview

The Internet Archive Download mode allows you to download searchable text files and PDFs from items hosted on the Internet Archive (archive.org). It specifically targets OCR-processed text and searchable PDFs, making it ideal for researchers, archivists, and anyone working with public domain or openly licensed materials.

## Prerequisites

The `internetarchive` Python library is automatically installed when you run `setup.bat` or manually install from `requirements.txt`.

## Input Methods

There are **three ways** to specify which Internet Archive items to download:

### Method 1: Single Item (Default)

1. Open Batchin' Camaro
2. From the "Mode" dropdown, select **"Internet Archive Download"**
3. Enter a single item identifier or URL in the **"Item identifier"** field

Every item on Internet Archive has a unique identifier. You can find this in the URL:
- Example URL: `https://archive.org/details/georgewashingt00ledggoog`
- Item identifier: `georgewashingt00ledggoog`

### Method 2: Multi-Line URL Input (NEW - Recommended for Multiple Items)

Perfect for pasting multiple archive.org URLs directly:

1. Check the **"Use multi-line URL input"** checkbox
2. A text area will appear
3. Paste your archive.org URLs, **one per line**
4. Lines starting with `#` are treated as comments and ignored

**Example:**
```
# Paste your URLs here
https://archive.org/details/LaurelCanyonHistory_201810
https://archive.org/details/georgewashingt00ledggoog
https://archive.org/details/alicesadventures19033gut

# You can also use direct item IDs
ItemID123
ItemID456
```

**Supported URL formats:**
- Full URL: `https://archive.org/details/ItemID`
- Short URL: `archive.org/details/ItemID`
- Direct ID: `ItemID`

### Method 3: CSV File

For bulk downloads with metadata:

1. Check the **"Use CSV with links"** checkbox
2. Click **"Open..."** to select your CSV file
3. Select the column containing Internet Archive URLs

See `CSV_DOWNLOADER_GUIDE.md` for detailed CSV usage instructions.

## Configure Download Settings

### File Format (NEW - Searchable Text Only)

Choose which types of **searchable/OCR-processed** files to download:

- **OCR Text**: Downloads text files with OCR-extracted content
  - Formats: "Text", "OCR Search Text", "Abbyy GZ", "DjVu Text"
  - These are plain text files created from OCR processing
  - Best for: Text analysis, search, natural language processing
  
- **PDF with Text**: Downloads searchable PDF files with embedded text layer
  - Formats: "Text PDF", "PDF WITH TEXT", "Additional Text PDF"
  - These are PDFs where you can select and search text
  - Best for: Reading, citation, preserving original layout
  
- **Both**: Downloads both OCR text files AND searchable PDFs

**Important:** This tool specifically targets searchable/parseable files, NOT image-only PDFs or plain TXT files without OCR metadata.

### Rate Limiting

Set the delay between file downloads to avoid overloading Internet Archive's servers:
- **Default**: 1.5 seconds (recommended)
- **Recommended range**: 1-2 seconds
- Higher values are more respectful of the server but slower

### Additional Options

- **Create subdirectory for each item**: When checked, creates a separate folder for each item's files
- **Parse HTML in .txt files**: Automatically converts HTML-formatted text files to clean plain text

## Select Output Directory

Click **"Browse..."** next to "Output directory" to select where downloaded files should be saved.

## Preview Files (Optional)

Click the **"Preview"** or **"Refresh Preview"** button to see:
- Item title (for single item mode)
- List of items to download (for multi-URL or CSV modes)
- Number of files that match your format filter
- File sizes
- Total number of files to download

This helps you verify you're downloading the correct items before starting.

## Download Files

Click **"Run"** or **"Build Output"** to start downloading. The application will:
1. Connect to Internet Archive
2. For each item, list all available files
3. Filter files based on your format selection (OCR Text / PDF with Text)
4. Download each file one at a time
5. Wait the specified delay between downloads
6. Apply HTML parsing to .txt files if enabled
7. Show progress updates in the status bar

## Check Results

After downloading completes, you'll see:
- Total number of files downloaded
- Location of the downloaded files (with subdirectories if enabled)

## Examples

### Example 1: Download OCR Text from Multiple Books (NEW)

**Using multi-line URL input:**

1. Select mode: **"Internet Archive Download"**
2. Check **"Use multi-line URL input"**
3. Paste URLs in the text area:
   ```
   https://archive.org/details/alicesadventures19033gut
   https://archive.org/details/prideandprejudic00austgoog
   https://archive.org/details/mobydickorwhale01melvgoog
   ```
4. Select format: **OCR Text**
5. Set delay: **1.5 seconds**
6. Check **"Create subdirectory for each item"**
7. Choose output directory
8. Click **Run**

Result: Downloads OCR-processed text files for all three books into separate folders.

### Example 2: Download Searchable PDFs from a Single Item

1. Select mode: **"Internet Archive Download"**
2. Enter item: `https://archive.org/details/nasa-technical-reports-server`
3. Select format: **PDF with Text**
4. Set delay: **2 seconds** (be extra respectful for large items)
5. Choose output directory
6. Click **Run**

### Example 3: Bulk Download from CSV

See `CSV_DOWNLOADER_GUIDE.md` for detailed examples of CSV-based downloads.

## Best Practices

### Rate Limiting
- **Always use at least 1 second delay** between downloads
- For large items (100+ files), consider using 2-3 seconds
- Internet Archive is a non-profit; be respectful of their bandwidth

### File Selection
- Use the Preview feature to check what files will be downloaded
- **OCR Text** files are typically smaller and faster to download
- **PDF with Text** files preserve original formatting but are larger
- Very large items may take hours to download completely

### Multi-URL Input Tips
- One URL per line - don't put multiple URLs on the same line
- Use `#` at the start of a line for comments or notes
- Remove the placeholder comments before running
- Keep the list in a text file for reuse

### Error Handling
If a download fails:
- Check your internet connection
- Verify the item identifier is correct
- Try increasing the delay between downloads
- Some files may be restricted or unavailable; the tool will continue with remaining files

## Troubleshooting

### "Failed to get item"
- Verify the item identifier is correct (copy from the URL)
- Check your internet connection
- The item may not exist or may be private

### "No files found" or "No OCR Text/PDF with Text files found"
- The item may not have OCR-processed text or searchable PDFs
- Some items only have image-only PDFs or regular text files
- Try changing the format filter to "Both" to see all available options
- Use Preview to see what files are available and their formats
- Some very old digitizations may not have OCR text available

### "No valid Internet Archive URLs found" (Multi-URL mode)
- Make sure URLs are on separate lines (one per line)
- Check that URLs contain "archive.org/details/"
- Remove any extra spaces or characters
- Ensure you've removed or commented out the placeholder text

### "Download failed"
- Your internet connection may have dropped
- Internet Archive servers may be temporarily unavailable
- Try again with a longer delay
- Some files may be corrupted; the tool will continue with remaining files

### Multi-URL text area is not visible
- Make sure you've checked the **"Use multi-line URL input"** checkbox
- The text area appears below the checkbox when enabled
- If using CSV mode, uncheck "Use CSV with links" first

### Wrong files being downloaded
- Check the format filter - it should be "OCR Text" or "PDF with Text"
- Preview the item first to see available file formats
- Some items use different format naming conventions
- Try using "Both" to get all searchable text formats
- Your internet connection may have dropped
- Internet Archive servers may be temporarily unavailable
- Try again with a longer delay

## Technical Details

### Supported File Formats

The tool specifically targets **searchable/OCR-processed** files:

#### OCR Text Formats
- **"Text"**: Plain text files (usually OCR output)
- **"OCR Search Text"**: Explicitly marked OCR text files
- **"Abbyy GZ"**: Compressed ABBYY FineReader OCR output
- **"DjVu Text"**: Text extracted from DjVu format
- Files with "ocr" in the format name (case-insensitive)

#### PDF with Text Formats
- **"Text PDF"**: PDFs with embedded searchable text layer
- **"PDF WITH TEXT"**: Explicitly marked searchable PDFs
- **"Additional Text PDF"**: Supplementary searchable PDF versions
- Files with both "text" and "pdf" in the format name (case-insensitive)

**Note:** Regular "PDF" (image-only) and plain "TXT" files without OCR metadata are NOT included unless they match the above criteria.

### Input URL Formats

All three formats are supported:
```
https://archive.org/details/ItemID    # Full HTTPS URL
http://archive.org/details/ItemID     # HTTP URL
archive.org/details/ItemID            # Domain without protocol
www.archive.org/details/ItemID        # With www subdomain
ItemID                                # Direct item identifier
```

### Multi-URL Input Parsing
- Lines are processed one at a time
- Empty lines are skipped
- Lines starting with `#` are treated as comments and skipped
- Each line is parsed to extract the item ID
- Duplicate item IDs are kept (may download same item multiple times)

### Rate Limiting Implementation
The tool uses Python's `time.sleep()` to pause between downloads:
```python
# Download file 1
time.sleep(delay)  # Wait configured delay
# Download file 2
time.sleep(delay)  # Wait configured delay
# Download file 3
# ... and so on
```

This ensures respectful usage of Internet Archive's infrastructure.

## Additional Resources

- [Internet Archive](https://archive.org/)
- [Internet Archive Python Library Documentation](https://archive.org/developers/internetarchive/quickstart.html)
- [Internet Archive Search](https://archive.org/search.php)

## Legal and Ethical Considerations

- **Respect copyright**: Only download items in the public domain or with appropriate licenses
- **Terms of Service**: Follow Internet Archive's terms of service
- **Fair use**: Download only what you need for research or educational purposes
- **Attribution**: Give proper credit to Internet Archive and content creators
