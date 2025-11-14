# CSV-Based Internet Archive Downloader

## Overview

This feature allows you to batch download files from multiple Internet Archive items using a CSV file containing item URLs or IDs.

## Features

1. **CSV Input**: Upload a CSV file with Internet Archive links
2. **Subdirectory Organization**: Optionally create a subdirectory for each item
3. **HTML Parsing**: Automatically parse HTML content in .txt files to extract clean text
4. **Rate Limiting**: Configurable delay between downloads to respect server limits
5. **Format Selection**: Choose to download Text, PDF, or Both formats

## Usage

### 1. Prepare Your CSV File

Create a CSV file with Internet Archive links. Example:

```csv
link,title
https://archive.org/details/LaurelCanyonHistory_201810,Laurel Canyon History
https://archive.org/details/georgewashingt00ledggoog,George Washington Biography
LaurelCanyonHistory_201810,Laurel Canyon (direct ID)
```

The CSV should have:
- A header row
- At least one column containing Internet Archive URLs or item IDs
- URLs can be in full format (`https://archive.org/details/ITEM_ID`) or just the item ID

### 2. Configure Download Settings

1. Open Batchin' Camaro
2. Select mode: **"Internet Archive Download"**
3. Check **"Use CSV with links"**
4. Click **"Open…"** to select your CSV file
5. Select the column containing the links (auto-detected if column name includes "link", "url", or "archive")

### 3. Configure Output Options

- **Output directory**: Choose where files will be saved (defaults to `Documents\batchin\`)
- **Create subdirectory for each item**: When checked, creates a folder for each item ID
- **Parse HTML in .txt files**: When checked, extracts plain text from HTML-formatted .txt files
- **File format**: Choose Text, PDF, or Both
- **Delay between downloads**: Set in seconds (1-2 recommended)

### 4. Run the Download

Click **"Run"** or **"Build Output"** to start downloading.

## Output Structure

### With Subdirectories (Recommended)
```
Documents/batchin/
├── LaurelCanyonHistory_201810/
│   ├── document1.txt
│   ├── document2.txt
│   └── image.pdf
├── georgewashingt00ledggoog/
│   ├── biography.txt
│   └── cover.pdf
```

### Without Subdirectories
```
Documents/batchin/
├── document1.txt
├── document2.txt
├── image.pdf
├── biography.txt
└── cover.pdf
```

## HTML Parsing Feature

Internet Archive sometimes serves HTML files with a .txt extension. When **"Parse HTML in .txt files"** is enabled:

### Before (Raw HTML):
```html
<!DOCTYPE html>
<html>
<head><title>Document</title></head>
<body>
<h1>Title</h1>
<p>Content here.</p>
<script>console.log('script');</script>
</body>
</html>
```

### After (Parsed Text):
```
Document
Title
Content here.
```

The parser:
- Removes all HTML tags
- Extracts clean text content
- Removes `<script>` and `<style>` blocks
- Preserves document structure with line breaks

## Tips

1. **Rate Limiting**: Always use at least 1 second delay to avoid overwhelming the server
2. **Large Collections**: For items with many files, consider downloading only the format you need
3. **Subdirectories**: Enable this when downloading from multiple items to keep files organized
4. **Preview**: Use the Preview button to see what files will be downloaded before starting
5. **Error Handling**: If a download fails for one item, the tool continues with remaining items

## Troubleshooting

### "No valid Internet Archive links found"
- Check that your CSV column contains proper URLs or item IDs
- Verify the column name is selected correctly

### "Failed to get item"
- Check your internet connection
- Verify the item ID is correct
- The item may not exist or may be private

### HTML not being parsed
- Ensure "Parse HTML in .txt files" is checked
- The file must have HTML markers (`<html>`, `<body>`, or `<!doctype>`)
- BeautifulSoup must be installed (`pip install beautifulsoup4`)

## Technical Details

### Supported URL Formats
- Full URL: `https://archive.org/details/ITEM_ID`
- Short URL: `archive.org/details/ITEM_ID`
- Direct ID: `ITEM_ID`

### Dependencies
- `internetarchive`: For downloading files
- `beautifulsoup4`: For HTML parsing

### Column Name Detection
The tool automatically detects columns named:
- link, url, archive, ia_link, internet_archive, source, href (case-insensitive)
