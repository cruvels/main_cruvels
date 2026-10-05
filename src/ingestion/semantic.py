"""
Semantic understanding engine for Phase 1.
Performs:
1. Document Type Classification (Judgment, Contract, Agreement, Legal Notice, Petition, etc.) with confidence.
2. Entity Extraction (person, organization, court, judge, company, date, amount, location, statute, section, case, party).
3. Concept Extraction (breach, limitation, arbitration, jurisdiction, damages, indemnity, termination, obligations, etc.).
4. Claim Extraction (factual/legal/procedural claims with confidence and section mapping).
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.model import get_llm
from .models import ClaimModel, ConceptModel, DocumentType, EntityModel

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """
You are an expert legal AI document classifier.
Classify the following legal document excerpt into EXACTLY ONE of the following types:
- Judgment
- Contract
- Agreement
- Legal Notice
- Petition
- Written Statement
- Research Document
- Case File
- Draft
- Template
- Correspondence
- Other

Output ONLY a JSON object with this exact structure:
{
  "document_type": "Contract",
  "confidence": 0.95,
  "rationale": "Clear offer, acceptance, consideration, and party obligations present."
}
"""

SEMANTIC_EXTRACTION_PROMPT = """
You are a legal AI semantic extraction engine. Analyze the legal text excerpt and extract:
1. Entities: (entity_type must be one of: person, organization, court, judge, company, date, amount, location, statute, section, case, party)
2. Concepts: (legal topics such as breach, limitation, arbitration, jurisdiction, damages, indemnity, termination, obligations, governing law, confidentiality)
3. Claims: (factual assertions, legal findings, or procedural claims made in the text)

Return ONLY valid JSON matching this exact structure:
{
  "entities": [
    {"entity_type": "company", "name": "ABC Pvt Ltd", "confidence": 0.98, "context": "Party of the first part"},
    {"entity_type": "amount", "name": "₹25,00,000", "confidence": 0.95, "context": "Contract consideration"}
  ],
  "concepts": [
    {"topic": "termination", "description": "30 days written notice required for termination", "relevance_score": 0.9},
    {"topic": "arbitration", "description": "Disputes resolved via arbitration in New Delhi", "relevance_score": 0.95}
  ],
  "claims": [
    {"claim_text": "The respondent failed to deliver goods within the stipulated period.", "claim_type": "factual", "confidence": 0.92},
    {"claim_text": "Section 73 of the Indian Contract Act entitles the claimant to compensation.", "claim_type": "legal", "confidence": 0.95}
  ]
}
"""


def _clean_json_output(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def classify_document(text: str) -> Tuple[DocumentType, float]:
    """Classifies document type using the LLM. Returns (DocumentType, confidence)."""
    if not text.strip():
        return DocumentType.OTHER, 0.0

    snippet = text[:3500]
    llm = get_llm()

    try:
        messages = [
            SystemMessage(content=CLASSIFICATION_PROMPT),
            HumanMessage(content=f"Document excerpt:\n{snippet}\n\nClassify this document."),
        ]
        response = llm.invoke(messages)
        content = _clean_json_output(response.content)
        data = json.loads(content)

        doc_type_str = data.get("document_type", "Other")
        confidence = float(data.get("confidence", 0.5))

        # Map to enum
        for dt in DocumentType:
            if dt.value.lower() == doc_type_str.lower():
                return dt, confidence

        return DocumentType.OTHER, confidence
    except Exception as e:
        logger.warning("Document classification fallback due to error: %s", e)
        # Fast heuristic fallback
        lower_text = snippet.lower()
        if "in the court of" in lower_text or "judgment" in lower_text or "versus" in lower_text:
            return DocumentType.JUDGMENT, 0.70
        elif "agreement" in lower_text:
            return DocumentType.AGREEMENT, 0.70
        elif "contract" in lower_text:
            return DocumentType.CONTRACT, 0.70
        elif "legal notice" in lower_text or "under section" in lower_text and "notice" in lower_text:
            return DocumentType.LEGAL_NOTICE, 0.70
        return DocumentType.OTHER, 0.30


def extract_semantics(
    text: str, document_id: str, section_id: str = None
) -> Tuple[List[EntityModel], List[ConceptModel], List[ClaimModel]]:
    """Extracts structured entities, concepts, and claims from legal text."""
    if not text.strip():
        return [], [], []

    snippet = text[:4000]
    llm = get_llm()

    entities: List[EntityModel] = []
    concepts: List[ConceptModel] = []
    claims: List[ClaimModel] = []

    try:
        messages = [
            SystemMessage(content=SEMANTIC_EXTRACTION_PROMPT),
            HumanMessage(content=f"Document excerpt:\n{snippet}\n\nExtract entities, concepts, and claims in JSON format."),
        ]
        response = llm.invoke(messages)
        content = _clean_json_output(response.content)
        data = json.loads(content)

        raw_entities = data.get("entities", [])
        for idx, ent in enumerate(raw_entities):
            if isinstance(ent, dict) and "name" in ent and "entity_type" in ent:
                entities.append(
                    EntityModel(
                        entity_id=f"{document_id}_ent_{idx}",
                        document_id=document_id,
                        entity_type=ent["entity_type"].lower(),
                        name=ent["name"],
                        confidence=float(ent.get("confidence", 0.9)),
                        context=ent.get("context"),
                    )
                )

        raw_concepts = data.get("concepts", [])
        for idx, conc in enumerate(raw_concepts):
            if isinstance(conc, dict) and "topic" in conc:
                concepts.append(
                    ConceptModel(
                        concept_id=f"{document_id}_cnc_{idx}",
                        document_id=document_id,
                        topic=conc["topic"].lower(),
                        description=conc.get("description"),
                        relevance_score=float(conc.get("relevance_score", 0.85)),
                    )
                )

        raw_claims = data.get("claims", [])
        for idx, clm in enumerate(raw_claims):
            if isinstance(clm, dict) and "claim_text" in clm:
                claims.append(
                    ClaimModel(
                        claim_id=f"{document_id}_clm_{idx}",
                        document_id=document_id,
                        section_id=section_id,
                        claim_text=clm["claim_text"],
                        claim_type=clm.get("claim_type", "factual"),
                        confidence=float(clm.get("confidence", 0.85)),
                    )
                )

    except Exception as e:
        logger.warning("Semantic extraction fallback due to LLM error: %s", e)
        # Deterministic regex fallback for key legal patterns
        # 1. Dates
        dates = re.findall(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b", snippet, re.IGNORECASE)
        for idx, d in enumerate(set(dates)):
            entities.append(
                EntityModel(
                    entity_id=f"{document_id}_ent_d_{idx}",
                    document_id=document_id,
                    entity_type="date",
                    name=d,
                    confidence=0.9,
                    context="Extracted from text",
                )
            )

        # 2. Amounts
        amounts = re.findall(r"(?:Rs\.?|INR|₹|\$)\s*[\d,]+(?:\.\d{2})?(?:\s*(?:lakh|crore|million|billion))?", snippet, re.IGNORECASE)
        for idx, a in enumerate(set(amounts)):
            entities.append(
                EntityModel(
                    entity_id=f"{document_id}_ent_a_{idx}",
                    document_id=document_id,
                    entity_type="amount",
                    name=a,
                    confidence=0.9,
                    context="Extracted from text",
                )
            )

        # 3. Concepts heuristic
        concept_keywords = ["termination", "arbitration", "jurisdiction", "confidentiality", "indemnity", "breach", "damages", "governing law", "intellectual property", "severability", "liability"]
        for idx, kw in enumerate(concept_keywords):
            if kw in snippet.lower():
                concepts.append(
                    ConceptModel(
                        concept_id=f"{document_id}_cnc_h_{idx}",
                        document_id=document_id,
                        topic=kw,
                        description=f"Mentions of {kw} identified in document text",
                        relevance_score=0.85,
                    )
                )

        # 4. Claims heuristic (actionable obligations, legal warranties, factual claims)
        sentences = re.split(r"(?<=[.!?])\s+", snippet)
        claim_patterns = [
            (r"\b(shall not|shall|must|agrees? to|undertakes? to)\b", "obligation"),
            (r"\b(warrants? that|represents? that|certifies? that)\b", "legal"),
            (r"\b(is entitled to|reserves? the right|has the right to)\b", "legal"),
            (r"\b(in no event shall|neither party shall|liable for)\b", "procedural"),
            (r"\b(developed|built|managed|implemented|recognized|ranked)\b", "factual"),
        ]
        extracted_claim_count = 0
        for sent in sentences:
            sent_clean = sent.strip()
            if len(sent_clean) < 25 or len(sent_clean) > 280:
                continue
            for pat, ctype in claim_patterns:
                if re.search(pat, sent_clean, re.IGNORECASE):
                    claims.append(
                        ClaimModel(
                            claim_id=f"{document_id}_clm_h_{extracted_claim_count}",
                            document_id=document_id,
                            section_id=section_id,
                            claim_text=sent_clean,
                            claim_type=ctype,
                            confidence=0.88,
                        )
                    )
                    extracted_claim_count += 1
                    break
            if extracted_claim_count >= 8:
                break

    return entities, concepts, claims
