#!/usr/bin/env python3
"""
md2pdf.py — Convert Markdown to a styled HandWave PDF.

Pipeline:
  1. markdown → HTML  (Python 'markdown' lib, tables + fenced_code extensions)
  2. HTML → PDF       (Chrome headless --print-to-pdf)

Usage:
  python3 md2pdf.py input.md output.pdf

Dependencies:
  pip install markdown
  Google Chrome / Chromium installed (google-chrome or chromium-browser in PATH)
"""

import sys
import os
import subprocess
import tempfile
import shutil
import markdown

# ---------------------------------------------------------------------------
# Style — HandWave brand colours: primary #0066cc, dark #004499
# ---------------------------------------------------------------------------
CSS = """
@page {
    size: A4;
    margin: 2cm 2.5cm 2.2cm 2.5cm;
    @bottom-center { content: counter(page); font-size: 9pt; color: #666; }
}
body {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #222;
}
h1 {
    font-size: 22pt;
    border-bottom: 2px solid #0066cc;
    padding-bottom: 6px;
    color: #0066cc;
    margin-top: 0;
}
h2 {
    font-size: 16pt;
    color: #004499;
    margin-top: 1.6em;
    border-bottom: 1px solid #ccc;
    padding-bottom: 4px;
}
h3 {
    font-size: 13pt;
    color: #333;
    margin-top: 1.3em;
}
h4 {
    font-size: 11pt;
    color: #0066cc;
    margin-top: 1.1em;
}
p { margin: 0.6em 0; }
a { color: #0066cc; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 10pt;
}
th {
    background: #0066cc;
    color: white;
    padding: 6px 10px;
    text-align: left;
    font-weight: 600;
}
td {
    border: 1px solid #ccc;
    padding: 5px 10px;
    vertical-align: top;
}
tr:nth-child(even) td { background: #f5f8fc; }
code {
    background: #f0f0f0;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 10pt;
    font-family: 'Courier New', monospace;
}
pre {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 12px 16px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 9pt;
    line-height: 1.4;
}
pre code { background: none; color: inherit; padding: 0; }
blockquote {
    border-left: 4px solid #0066cc;
    margin: 1em 0;
    padding: 0.5em 1em;
    background: #f5f8fc;
    color: #444;
}
strong { color: #0066cc; }
hr { border: none; border-top: 1px solid #ccc; margin: 1.5em 0; }
ul, ol { margin: 0.5em 0; padding-left: 1.5em; }
li { margin: 0.25em 0; }
"""

CHROME_CANDIDATES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]


def find_chrome():
    for candidate in CHROME_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError(
        "Chrome/Chromium not found. Install google-chrome or chromium-browser."
    )


def convert(md_path: str, pdf_path: str):
    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()

    html_body = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "toc"]
    )
    full_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    chrome = find_chrome()
    pdf_abs = os.path.abspath(pdf_path)

    with tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(full_html)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                f"--print-to-pdf={pdf_abs}",
                f"--print-to-pdf-no-header",
                f"file://{tmp_path}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Chrome exited {result.returncode}:\n{result.stderr}"
            )
    finally:
        os.unlink(tmp_path)

    print(f"✅ {pdf_abs}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} input.md output.pdf")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
