"""
Specialized document parsers for PDF, DOCX, TXT, and Images.
Returns normalized document structure, page details, and handles OCR detection when needed.
"""
from __future__ import annotations

import logging
import re
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf as fitz

from src.config import get_settings
from .models import DocumentHierarchy, ParagraphModel, SectionModel, TableModel
from .ocr import ocr_image

logger = logging.getLogger(__name__)


class DocumentParser(ABC):
    """Abstract interface for format-specific legal document parsers."""

    @abstractmethod
    def parse(self, file_path: Path, doc_id: str) -> Dict[str, Any]:
        """
        Parses document and returns normalized structure:
        {
            "document_id": "...",
            "text": "...",
            "pages": [{"page_number": 1, "text": "...", "source_type": "native", "confidence": 1.0}],
            "structure": DocumentHierarchy,
            "metadata": {}
        }
        """
        pass


def _detect_hierarchy_from_lines(lines: List[str], doc_id: str, default_page: int = 1) -> DocumentHierarchy:
    """
    Analyzes line patterns to detect titles, sections, subsections, numbered clauses,
    citations, footnotes, and signature blocks.
    """
    sections: List[SectionModel] = []
    current_section: Optional[SectionModel] = None
    title = ""
    citations: List[str] = []
    footnotes: List[str] = []
    signature_block_detected = False

    # Regex patterns for legal structure detection
    section_pattern = re.compile(r"^(SECTION|ARTICLE|CLAUSE|\b[IVXLCDM]+\.|\b\d+(\.\d+)*\b)\s+.*", re.IGNORECASE)
    clause_pattern = re.compile(r"^(\(?\d+[\.\)]|\([a-z]\)|\b[A-Z]\.)\s+(.*)")
    citation_pattern = re.compile(
        r"(\b\d{4}\s+(?:SCC|SCR|AIR|Scale|Comp\s*Cas|CrLJ|SCC\s*OnLine)\s+\w+|\b\d+\s+U\.S\.\s+\d+|\b\[\d{4}\]\s+[A-Z]+\s+\d+|\bSection\s+\d+\s+of\s+[A-Za-z\s]+Act)",
        re.IGNORECASE,
    )
    sig_pattern = re.compile(r"(IN\s+WITNESS\s+WHEREOF|SIGNATURES?|SIGNED\s+AND\s+DELIVERED|ADVOCATE\s+FOR)", re.IGNORECASE)

    current_para_text = []
    para_idx = 0
    sec_idx = 0

    def check_citations(text_to_check: str):
        found_cits = citation_pattern.findall(text_to_check)
        for c in found_cits:
            if isinstance(c, tuple):
                c = c[0]
            if c and c not in citations:
                citations.append(c)

    def flush_paragraph():
        nonlocal current_para_text, para_idx, current_section
        if not current_para_text:
            return
        p_text = " ".join(current_para_text).strip()
        current_para_text = []
        if not p_text:
            return

        is_clause = bool(clause_pattern.match(p_text))
        clause_match = clause_pattern.match(p_text)
        clause_num = clause_match.group(1) if clause_match else None

        check_citations(p_text)

        para_model = ParagraphModel(
            paragraph_id=f"{doc_id}_p_{para_idx}",
            section_id=current_section.section_id if current_section else None,
            page_number=default_page,
            text=p_text,
            order_index=para_idx,
            is_clause=is_clause,
            clause_number=clause_num,
        )
        para_idx += 1

        if current_section:
            current_section.paragraphs.append(para_model)
        else:
            # Create a default preamble/general section
            current_section = SectionModel(
                section_id=f"{doc_id}_sec_0",
                title="Preamble / Introduction",
                level=1,
                page_number=default_page,
                order_index=0,
                paragraphs=[para_model],
            )
            sections.append(current_section)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue

        check_citations(stripped)

        if sig_pattern.search(stripped):
            signature_block_detected = True

        if not title and len(stripped) < 150 and not stripped.endswith("."):
            title = stripped
            continue

        # Check if line is a section heading: headings are generally short and don't end in period/full stop sentences
        is_sec_heading = (
            (stripped.isupper() and len(stripped) < 100 and len(stripped.split()) <= 10)
            or (section_pattern.match(stripped) and len(stripped) < 100 and not stripped.endswith("."))
            or (stripped.endswith(":") and len(stripped) < 80)
        )

        if is_sec_heading:
            flush_paragraph()
            sec_idx += 1
            sec_id = f"{doc_id}_sec_{sec_idx}"
            level = 2 if "." in stripped.split()[0] and len(stripped.split()[0].split(".")) > 2 else 1
            current_section = SectionModel(
                section_id=sec_id,
                title=stripped,
                level=level,
                page_number=default_page,
                order_index=sec_idx,
                paragraphs=[],
            )
            sections.append(current_section)
        else:
            current_para_text.append(stripped)

    flush_paragraph()

    return DocumentHierarchy(
        title=title or "Untitled Document",
        sections=sections,
        tables=[],
        footnotes=footnotes,
        citations=citations,
        signature_block_detected=signature_block_detected,
    )


class PDFParser(DocumentParser):
    """Parses PDF documents, extracting native text per page with automatic OCR fallback for scanned pages."""

    def parse(self, file_path: Path, doc_id: str) -> Dict[str, Any]:
        settings = get_settings()
        min_conf = settings.get("ingestion", {}).get("min_confidence", 0.60)
        doc = fitz.open(str(file_path))

        pages = []
        all_lines = []

        for i, page in enumerate(doc):
            page_num = i + 1
            native_text = page.get_text("text").strip()

            if native_text and len(native_text) > 30:
                pages.append({
                    "page_number": page_num,
                    "text": native_text,
                    "source_type": "native",
                    "confidence": 1.0,
                })
                all_lines.extend(native_text.splitlines())
            else:
                # Scanned or image-only page -> Run OCR
                logger.info("PDF page %d of %s has no native text, invoking PaddleOCR", page_num, file_path.name)
                ocr_text = ""
                ocr_conf = 0.0
                temp_img = Path(tempfile.gettempdir()) / f"page_ocr_{page_num}_{doc_id}.png"
                try:
                    pix = page.get_pixmap(dpi=200)
                    pix.save(str(temp_img))
                    ocr_res = ocr_image(str(temp_img), page_number=page_num)
                    ocr_text = ocr_res.text
                    ocr_conf = ocr_res.confidence
                except Exception as e:
                    logger.warning("OCR failed on page %d of %s: %s", page_num, file_path.name, e)
                finally:
                    if temp_img.exists():
                        try:
                            temp_img.unlink()
                        except Exception:
                            pass

                pages.append({
                    "page_number": page_num,
                    "text": ocr_text,
                    "source_type": "ocr",
                    "confidence": ocr_conf,
                })
                all_lines.extend(ocr_text.splitlines())

        doc.close()
        full_text = "\n\n".join(p["text"] for p in pages if p["text"].strip())
        structure = _detect_hierarchy_from_lines(all_lines, doc_id, default_page=1)

        return {
            "document_id": doc_id,
            "text": full_text,
            "pages": pages,
            "structure": structure,
            "metadata": {
                "page_count": len(pages),
                "is_scanned": any(p["source_type"] == "ocr" for p in pages),
            },
        }


class DOCXParser(DocumentParser):
    """Parses DOCX documents, preserving table data and paragraphs."""

    def parse(self, file_path: Path, doc_id: str) -> Dict[str, Any]:
        from docx import Document as DocxDocument

        docx_doc = DocxDocument(str(file_path))
        lines = []
        tables: List[TableModel] = []

        for p in docx_doc.paragraphs:
            if p.text.strip():
                lines.append(p.text.strip())

        for idx, tbl in enumerate(docx_doc.tables):
            table_rows = []
            for row in tbl.rows:
                table_rows.append([cell.text.strip() for cell in row.cells])
            if table_rows:
                tables.append(
                    TableModel(
                        table_id=f"{doc_id}_tbl_{idx}",
                        page_number=1,
                        headers=table_rows[0],
                        rows=table_rows[1:] if len(table_rows) > 1 else [],
                    )
                )

        full_text = "\n\n".join(lines)
        structure = _detect_hierarchy_from_lines(lines, doc_id, default_page=1)
        structure.tables = tables

        return {
            "document_id": doc_id,
            "text": full_text,
            "pages": [{"page_number": 1, "text": full_text, "source_type": "native", "confidence": 1.0}],
            "structure": structure,
            "metadata": {"paragraph_count": len(lines), "table_count": len(tables)},
        }


class TXTParser(DocumentParser):
    """Parses plain text legal documents."""

    def parse(self, file_path: Path, doc_id: str) -> Dict[str, Any]:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        structure = _detect_hierarchy_from_lines(lines, doc_id, default_page=1)

        return {
            "document_id": doc_id,
            "text": text,
            "pages": [{"page_number": 1, "text": text, "source_type": "native", "confidence": 1.0}],
            "structure": structure,
            "metadata": {"line_count": len(lines)},
        }


class ImageParser(DocumentParser):
    """Parses image-based legal documents (PNG, JPG, JPEG) via OCR."""

    def parse(self, file_path: Path, doc_id: str) -> Dict[str, Any]:
        ocr_res = ocr_image(str(file_path), page_number=1)
        lines = ocr_res.text.splitlines()
        structure = _detect_hierarchy_from_lines(lines, doc_id, default_page=1)

        return {
            "document_id": doc_id,
            "text": ocr_res.text,
            "pages": [{
                "page_number": 1,
                "text": ocr_res.text,
                "source_type": "ocr",
                "confidence": ocr_res.confidence,
            }],
            "structure": structure,
            "metadata": {"ocr_confidence": ocr_res.confidence},
        }


_PARSER_MAP = {
    ".pdf": PDFParser,
    ".docx": DOCXParser,
    ".txt": TXTParser,
    ".png": ImageParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
}


def get_parser(file_extension: str) -> DocumentParser:
    ext = file_extension.lower()
    if ext not in _PARSER_MAP:
        raise ValueError(f"Unsupported file format '{ext}'. Supported formats: {list(_PARSER_MAP.keys())}")
    return _PARSER_MAP[ext]()
