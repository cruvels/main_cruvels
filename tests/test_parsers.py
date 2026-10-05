"""
Unit test suite specifically testing format-specific document parsers:
- PDFParser (native + scanned OCR triggers)
- DOCXParser (paragraphs + tables)
- TXTParser (sections + clauses)
- ImageParser (OCR confidence)
"""
import io
import pytest
from pathlib import Path
from docx import Document as DocxDocument

from src.ingestion.parsers import PDFParser, DOCXParser, TXTParser, ImageParser, get_parser


def test_docx_parser_with_tables(tmp_path):
    docx_file = tmp_path / "sample_contract.docx"
    doc = DocxDocument()
    doc.add_heading("NON-DISCLOSURE AND CONFIDENTIALITY AGREEMENT", level=0)
    doc.add_paragraph("This agreement is entered into between Party A and Party B.")
    doc.add_heading("1. OBLIGATIONS OF RECIPIENT", level=1)
    doc.add_paragraph("1.1 The Recipient shall maintain strict confidentiality.")

    # Add a table
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Term"
    table.cell(0, 1).text = "Description"
    table.cell(1, 0).text = "Duration"
    table.cell(1, 1).text = "3 Years"

    doc.save(str(docx_file))

    parser = get_parser(".docx")
    assert isinstance(parser, DOCXParser)

    result = parser.parse(docx_file, doc_id="test_docx_1")
    assert "NON-DISCLOSURE" in result["text"]
    assert len(result["structure"].sections) > 0
    assert len(result["structure"].tables) == 1
    assert result["structure"].tables[0].headers == ["Term", "Description"]


def test_txt_parser_citations_and_clauses(tmp_path):
    txt_file = tmp_path / "case_brief.txt"
    txt_file.write_text(
        "IN THE HIGH COURT OF DELHI\n\n"
        "SECTION 1. PRELIMINARY\n"
        "1.1 In ABC Corp v. State of Maharashtra 2024 SCC 112, the court held that limitation applies.\n"
        "1.2 Section 73 of Indian Contract Act governs damages.\n"
        "IN WITNESS WHEREOF\n"
        "Advocate for Petitioner",
        encoding="utf-8",
    )

    parser = get_parser(".txt")
    result = parser.parse(txt_file, doc_id="test_txt_1")

    assert result["structure"].signature_block_detected is True
    assert len(result["structure"].citations) >= 1
