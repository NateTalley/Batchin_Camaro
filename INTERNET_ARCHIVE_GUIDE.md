# Internet Archive Download Mode

This guide explains how to use the Internet Archive Download mode in Batchin' Camaro.

## Overview

The Internet Archive Download mode allows you to download text files and PDFs from items hosted on the Internet Archive (archive.org). This feature is useful for researchers, archivists, and anyone working with public domain or openly licensed materials.

## Prerequisites

The `internetarchive` Python library is automatically installed when you run `setup.bat` or manually install from `requirements.txt`.

## How to Use

### 1. Select the Mode

1. Open Batchin' Camaro
2. From the "Mode" dropdown, select **"Internet Archive Download"**

### 2. Enter Item Identifier

Every item on Internet Archive has a unique identifier. You can find this in the URL:
- Example URL: `https://archive.org/details/georgewashingt00ledggoog`
- Item identifier: `georgewashingt00ledggoog`

Enter the item identifier in the **"Item identifier"** field.

### 3. Configure Download Settings

#### File Format
Choose which types of files to download:
- **Text**: Download only text files (.txt)
- **PDF**: Download only PDF files (.pdf)
- **Both**: Download both text and PDF files

#### Rate Limiting
Set the delay between file downloads to avoid overloading Internet Archive's servers:
- **Default**: 1.5 seconds (recommended)
- **Recommended range**: 1-2 seconds
- Higher values are more respectful of the server but slower

### 4. Select Output Directory

Click **"Browse..."** next to "Output directory" to select where downloaded files should be saved.

### 5. Preview Files (Optional)

Click the **"Preview"** button to see:
- Item title
- List of available files that match your format filter
- File sizes
- Total number of files to download

This helps you verify you're downloading the correct item before starting.

### 6. Download Files

Click **"Run"** or **"Build Output"** to start downloading. The application will:
1. Connect to Internet Archive
2. List all files in the item
3. Filter files based on your format selection
4. Download each file one at a time
5. Wait the specified delay between downloads
6. Show progress updates in the status bar

### 7. Check Results

After downloading completes, you'll see:
- Total number of files downloaded
- Location of the downloaded files

## Examples

### Example 1: Download Text Files from a Book

1. Find a book on Internet Archive: `https://archive.org/details/alicesadventures19033gut`
2. Item identifier: `alicesadventures19033gut`
3. Select format: **Text**
4. Set delay: **1.5 seconds**
5. Choose output directory
6. Click **Run**

### Example 2: Download PDFs from a Collection Item

1. Find an item: `https://archive.org/details/nasa-technical-reports-server`
2. Item identifier: `nasa-technical-reports-server`
3. Select format: **PDF**
4. Set delay: **2 seconds** (be extra respectful for large items)
5. Choose output directory
6. Click **Run**

## Best Practices

### Rate Limiting
- **Always use at least 1 second delay** between downloads
- For large items (100+ files), consider using 2-3 seconds
- Internet Archive is a non-profit; be respectful of their bandwidth

### File Selection
- Use the Preview feature to check file sizes before downloading
- Very large items may take hours to download completely
- Consider downloading only the format you need (Text or PDF, not Both)

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

### "No files found"
- The item may not have any text or PDF files
- Try changing the format filter
- Use Preview to see what files are available

### "Download failed"
- Your internet connection may have dropped
- Internet Archive servers may be temporarily unavailable
- Try again with a longer delay

## Technical Details

### Supported File Formats
- **Text files**: Files with format "Text" or extension ".txt"
- **PDF files**: Files with format "PDF" or extension ".pdf"

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
