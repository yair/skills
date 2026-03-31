---
name: md-to-pdf
description: >
  Convert Markdown documents to styled PDF using Chrome headless rendering.
  Use when asked to generate a report, create a professional document, or
  produce a PDF from markdown content. Supports tables, code blocks, and
  custom CSS styling. Do NOT use weasyprint (produces blue-invaded output
  with cut images) — always use Chrome headless.
---

# Markdown to PDF Skill

## When to Use
- Generating professional reports from markdown (HandWave reports, trip summaries, analysis docs)
- Converting any `.md` file to a shareable PDF
- Producing client-facing documents that need consistent formatting

## When NOT to Use
- Quick text sharing → just send the markdown directly
- Internal documentation → markdown is fine, PDF adds no value
- If Chrome/Chromium is not installed on the machine

## Script

```bash
python3 scripts/md2pdf.py input.md output.pdf
```

The script:
1. Converts Markdown → HTML (Python `markdown` lib with tables + fenced_code extensions)
2. Wraps in a styled HTML template with professional CSS
3. Renders to PDF via Chrome headless (`--print-to-pdf`)

## Dependencies
- `pip install markdown` (Python markdown library)
- Google Chrome or Chromium in PATH (`google-chrome` or `chromium-browser`)

## Styling

Default CSS uses a professional blue theme (HandWave brand colors). To customize:
- Edit the `CSS` variable in `md2pdf.py`
- Or create a project-specific copy with different colors

Current defaults:
- A4 page size, 2cm margins
- Page numbers at bottom center
- Blue headers (#0066cc), dark blue subheaders (#004499)
- Clean table styling with blue header row
- Segoe UI / Helvetica Neue / Arial font stack

## Edge Cases
- **Chrome not found:** Script will fail with clear error. Install: `sudo apt install chromium-browser` or `google-chrome`
- **Images in markdown:** Use absolute paths or URLs. Relative paths resolve from the temp directory, not the source file location.
- **Very long documents:** Chrome headless handles them fine. No page limit.
- **Code blocks:** Styled with monospace font, grey background, proper wrapping.
- **Special characters:** UTF-8 fully supported (Albanian, Hebrew, emoji all work).

## Critical Warning
**Do NOT use weasyprint.** It produces blue-invaded output with cut images.
This was learned the hard way (Mar 20, 2026). Chrome headless is the only
reliable PDF renderer for our use case.

## Quality Gate
- [ ] PDF renders without errors
- [ ] Tables are properly formatted (not overflowing page width)
- [ ] Headers have correct hierarchy and styling
- [ ] Page numbers appear at bottom
- [ ] No blank pages at beginning or end
- [ ] File size is reasonable (<5MB for text-only docs)
