"""
Step 1: Extract text from PDF

Uses pymupdf4llm for structured markdown extraction (preserves tables, headings,
lists). Falls back to pdftotext for simple text-heavy PDFs, and OCR (tesseract)
for scanned pages.

Output: a .md file with structured content that Claude can parse well.
"""

import subprocess
import sys
import os

import pymupdf4llm
import pymupdf


def has_extractable_text(pdf_path: str) -> bool:
    """Check if PDF has actual text content (not just scanned images)."""
    doc = pymupdf.open(pdf_path)
    total_text = 0
    page_count = len(doc)
    for page in doc:
        total_text += len(page.get_text().strip())
    doc.close()
    # If less than 50 chars per page on average, it's likely scanned
    avg = total_text / max(page_count, 1)
    return avg > 50


def extract_with_pymupdf4llm(pdf_path: str) -> str:
    """Extract as structured markdown using pymupdf4llm."""
    md_text = pymupdf4llm.to_markdown(pdf_path)
    return md_text


def extract_with_pdftotext(pdf_path: str) -> str:
    """Fallback: extract with pdftotext (simpler but handles some edge cases)."""
    result = subprocess.run(
        ["pdftotext", pdf_path, "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def extract_with_ocr(pdf_path: str) -> str:
    """Fallback for scanned PDFs: convert pages to images and OCR with tesseract."""
    import tempfile
    doc = pymupdf.open(pdf_path)
    full_text = []
    tmp_dir = tempfile.mkdtemp(prefix="pdf_ocr_")

    for page_num, page in enumerate(doc):
        # Render page as image at 300 DPI
        pix = page.get_pixmap(dpi=300)
        img_path = os.path.join(tmp_dir, f"page_{page_num}.png")
        pix.save(img_path)

        # OCR with tesseract
        result = subprocess.run(
            ["tesseract", img_path, "stdout", "-l", "eng"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            full_text.append(f"## Page {page_num + 1}\n\n{result.stdout.strip()}")

        os.remove(img_path)

    doc.close()
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass
    return "\n\n".join(full_text)


def extract_pdf(pdf_path: str) -> tuple[str, str]:
    """
    Extract text from PDF using the best available method.
    Returns (text, method_used).
    """
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    # Try pymupdf4llm first (best quality — structured markdown)
    if has_extractable_text(pdf_path):
        print("  Method: pymupdf4llm (structured markdown)")
        text = extract_with_pymupdf4llm(pdf_path)
        if len(text.strip()) > 100:
            return text, "pymupdf4llm"

        # Fallback to pdftotext if pymupdf4llm produced little content
        print("  pymupdf4llm output too short, trying pdftotext...")
        text = extract_with_pdftotext(pdf_path)
        if len(text.strip()) > 100:
            return text, "pdftotext"

    # PDF is likely scanned — try OCR
    print("  PDF appears to be scanned, trying OCR...")
    has_tesseract = subprocess.run(
        ["which", "tesseract"], capture_output=True
    ).returncode == 0

    if has_tesseract:
        print("  Method: tesseract OCR")
        text = extract_with_ocr(pdf_path)
        if len(text.strip()) > 100:
            return text, "ocr"

    # Last resort: pdftotext anyway
    print("  Method: pdftotext (last resort)")
    text = extract_with_pdftotext(pdf_path)
    return text, "pdftotext"


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf_path:
        print("Usage: python step1_extract.py <pdf_path>")
        sys.exit(1)

    pdf_path = os.path.abspath(pdf_path)
    print(f"Extracting: {os.path.basename(pdf_path)}")

    text, method = extract_pdf(pdf_path)

    os.makedirs("output", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    out_path = f"output/{base_name}.md"

    # Also save .txt for backward compatibility
    txt_path = f"output/{base_name}.txt"

    with open(out_path, "w") as f:
        f.write(text)

    with open(txt_path, "w") as f:
        f.write(text)

    print(f"Extracted {len(text)} chars ({method}) -> {out_path}")
    return out_path


if __name__ == "__main__":
    main()
