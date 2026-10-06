"""RapidDoc Hierarchical Long-Document Summarization Engine.

Implements complete-document understanding using a Map-Reduce / Section-Aware
summarization strategy:

  Document
     ↓
  Complete Text Extraction (Prose cleaning, preserving structure & metrics)
     ↓
  Section & Boundary Detection (Headings, Markdown, Structural Paragraphs)
     ↓
  Adaptive Semantic Chunking (No silent truncation; complete coverage)
     ↓
  Map Phase: Section-Level Extraction / Model Summarization across ALL chunks
     ↓
  Reduce Phase: Global Document Synthesis & Cross-Section Aggregation
     ↓
  Structured Markdown Output (# Overview, ## Key Points, ## Details, ## Conclusion)
     ↓
  Validation, Metrics & Logging
"""

import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from RapidDoc.backend.app.config import settings
from RapidDoc.backend.app.services.document_text import clean_prose, split_prose_sentences
from RapidDoc.backend.app.services.local_models import summarize as local_model_summarize
from RapidDoc.backend.app.services.text_polish import ensure_sentence, split_sentences

logger = logging.getLogger(__name__)

# Structural heading detection
_HEADING_REGEX = re.compile(
    r"^(?:#{1,6}\s+|(?:\d+[\.\)]\s+)?(?:Abstract|Introduction|Background|Objective|Scope|"
    r"Methodology|Implementation|System Architecture|Design|Requirements|Analysis|"
    r"Findings|Results|Evaluation|Discussion|Performance|Security|Challenges|"
    r"Recommendations|Conclusion|Summary|Future Work|Appendix|References)\b)",
    re.IGNORECASE,
)

_NUMERICAL_OR_METRIC_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?%|\$\d+(?:,\d+)*(?:\.\d+)?|\d+(?:,\d+)+(?:\.\d+)?|\d+\s*(?:ms|sec|min|hours?|days?|MB|GB|KB|TB|users?|records?|queries|tokens?))\b",
    re.IGNORECASE,
)

_DATE_OR_YEAR_RE = re.compile(
    r"\b(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?|\b20\d{2}\b|\b19\d{2}\b|\bQ[1-4]\s*20\d{2}\b)",
    re.IGNORECASE,
)


class DocumentChunk:
    """Represents a discrete semantic chunk of the source document."""

    def __init__(self, index: int, title: str, text: str, token_estimate: int, is_terminal: bool = False):
        self.index = index
        self.title = title
        self.text = text
        self.token_estimate = token_estimate
        self.is_terminal = is_terminal
        self.intermediate_summary: str = ""
        self.key_facts: List[str] = []


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English text)."""
    return max(1, len(text) // 4)


def segment_document_into_sections(text: str) -> List[Tuple[str, str]]:
    """Segment document text into identifiable (heading, body) sections.
    
    If no explicit headings exist, breaks along substantive paragraph clusters.
    """
    lines = text.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    current_title = "Document Introduction"
    current_lines: List[str] = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            if current_lines:
                current_lines.append("")
            continue

        # Check if line looks like a section heading (short, matching heading pattern or Markdown #)
        if len(line_stripped) <= 100 and (_HEADING_REGEX.match(line_stripped) or line_stripped.startswith("#")):
            if any(l.strip() for l in current_lines):
                sections.append((current_title, current_lines))
            current_title = re.sub(r"^#+\s*", "", line_stripped)
            current_lines = []
        else:
            current_lines.append(line_stripped)

    if any(l.strip() for l in current_lines):
        sections.append((current_title, current_lines))

    # Convert line arrays to normalized section text
    result: List[Tuple[str, str]] = []
    for title, l_list in sections:
        body = "\n".join(l_list).strip()
        if body:
            result.append((title, body))

    # If the document had no distinct headings at all, return it as a single section
    if not result:
        result.append(("General Overview", text.strip()))

    return result


def create_chunks_for_document(
    text: str,
    target_chunk_tokens: int = 600,
    max_chunk_tokens: int = 900,
) -> List[DocumentChunk]:
    """Partition the complete document into bounded, semantically coherent chunks.
    
    Every single section is preserved; later parts of the document are NEVER dropped.
    """
    sections = segment_document_into_sections(text)
    chunks: List[DocumentChunk] = []
    chunk_index = 0

    for sec_idx, (sec_title, sec_body) in enumerate(sections):
        sec_tokens = estimate_tokens(sec_body)

        # If section fits within target chunk budget, keep as a single chunk
        if sec_tokens <= max_chunk_tokens:
            is_terminal = (sec_idx == len(sections) - 1)
            chunks.append(DocumentChunk(
                index=chunk_index,
                title=sec_title,
                text=sec_body,
                token_estimate=sec_tokens,
                is_terminal=is_terminal,
            ))
            chunk_index += 1
            continue

        # Otherwise, divide long section by paragraphs or sentences
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", sec_body) if p.strip()]
        current_para_group: List[str] = []
        current_tokens = 0
        sub_part = 1

        for para in paragraphs:
            para_tokens = estimate_tokens(para)
            if current_tokens + para_tokens > target_chunk_tokens and current_para_group:
                sub_title = f"{sec_title} (Part {sub_part})"
                chunk_text = "\n\n".join(current_para_group)
                chunks.append(DocumentChunk(
                    index=chunk_index,
                    title=sub_title,
                    text=chunk_text,
                    token_estimate=current_tokens,
                    is_terminal=False,
                ))
                chunk_index += 1
                sub_part += 1
                current_para_group = [para]
                current_tokens = para_tokens
            else:
                current_para_group.append(para)
                current_tokens += para_tokens

        if current_para_group:
            is_terminal = (sec_idx == len(sections) - 1)
            sub_title = f"{sec_title} (Part {sub_part})" if sub_part > 1 else sec_title
            chunk_text = "\n\n".join(current_para_group)
            chunks.append(DocumentChunk(
                index=chunk_index,
                title=sub_title,
                text=chunk_text,
                token_estimate=current_tokens,
                is_terminal=is_terminal,
            ))
            chunk_index += 1

    return chunks


def extract_key_metrics_and_dates(text: str) -> List[str]:
    """Find specific quantitative metrics, dates, and named entities."""
    findings = []
    for sentence in split_sentences(text):
        s_clean = sentence.strip()
        if len(s_clean) < 25 or len(s_clean) > 200:
            continue
        has_metric = bool(_NUMERICAL_OR_METRIC_RE.search(s_clean))
        has_date = bool(_DATE_OR_YEAR_RE.search(s_clean))
        if has_metric or has_date:
            cleaned = s_clean.rstrip(".")
            if cleaned not in findings:
                findings.append(cleaned)
        if len(findings) >= 8:
            break
    return findings


def score_and_extract_key_sentences(text: str, max_sentences: int = 3) -> List[str]:
    """Score sentences based on content density, key terms, and positional importance."""
    sentences = [s.strip() for s in split_sentences(text) if len(s.strip()) >= 25]
    if not sentences:
        return []

    words_all = re.findall(r"[A-Za-z][\w'-]{2,}", text.lower())
    freq: Dict[str, int] = {}
    for w in words_all:
        freq[w] = freq.get(w, 0) + 1

    scored = []
    total_sents = len(sentences)
    for idx, sent in enumerate(sentences):
        words = re.findall(r"[A-Za-z][\w'-]{2,}", sent.lower())
        if len(words) < 5 or len(words) > 75:
            continue

        raw_score = sum(freq.get(w, 0) for w in words) / max(1, len(words))
        # Fair positional weighting: front of section gets a modest bonus, and end of section gets an outcome bonus
        pos_bonus = 1.15 if idx == 0 else (1.10 if idx == total_sents - 1 else 1.0)
        # Numerical/metric bonus to keep factual findings
        metric_bonus = 1.25 if _NUMERICAL_OR_METRIC_RE.search(sent) else 1.0

        score = raw_score * pos_bonus * metric_bonus
        scored.append((score, idx, sent))

    scored.sort(key=lambda item: (-item[0], item[1]))
    # Pick top sentences and restore their natural chronological flow
    chosen = scored[:max_sentences]
    chosen.sort(key=lambda item: item[1])
    return [ensure_sentence(item[2]) for item in chosen]


def summarize_single_chunk(chunk: DocumentChunk) -> str:
    """Summarize an individual chunk using local model if loaded, falling back to extractive representation."""
    # Attempt local neural generation first
    try:
        model_out = local_model_summarize(chunk.text, max_new_tokens=96)
        if model_out and len(model_out.split()) >= 6:
            return model_out.strip()
    except Exception as exc:
        logger.debug("Local neural chunk summarization skipped: %s", exc)

    # Robust extractive section summarization
    sentences = score_and_extract_key_sentences(chunk.text, max_sentences=2)
    return " ".join(sentences) if sentences else chunk.text[:200]


def synthesize_markdown_summary(
    doc_title: str,
    chunks: List[DocumentChunk],
    full_text: str,
    original_char_count: int,
    start_time: float,
) -> Dict[str, Any]:
    """Reduce and synthesize intermediate chunk summaries into a cohesive, structured Markdown document."""
    # 1. Overview Synthesis (Context, main purpose from opening chunks)
    opening_text = chunks[0].text if chunks else full_text[:1200]
    overview_sentences = score_and_extract_key_sentences(opening_text, max_sentences=2)
    overview_paragraph = " ".join(overview_sentences) if overview_sentences else f"Comprehensive analysis of {doc_title}."

    # 2. Key Points Synthesis (Distributed across beginning, middle, and later parts of the document)
    key_points: List[str] = []
    seen_points = set()

    for chunk in chunks:
        # Extract 1 representative statement from every chunk
        pts = score_and_extract_key_sentences(chunk.text, max_sentences=1)
        for p in pts:
            p_clean = p.rstrip(".")
            # Avoid duplicate or near-identical bullet points
            norm = re.sub(r"[^a-z0-9]", "", p_clean.lower()[:40])
            if norm not in seen_points:
                seen_points.add(norm)
                key_points.append(p_clean)

    # Cap key points at 8 distinct points spanning the document
    if len(key_points) > 8:
        # Sample evenly across document chunks
        indices = [int(i * (len(key_points) - 1) / 7) for i in range(8)]
        key_points = [key_points[i] for i in sorted(set(indices))]

    # 3. Key Findings, Metrics, & Dates across the document
    metrics_and_dates = extract_key_metrics_and_dates(full_text)

    # 4. Section-by-Section Breakdown (Ensures every part is visible)
    section_breakdowns: List[Tuple[str, str]] = []
    for chunk in chunks:
        summary_body = chunk.intermediate_summary or summarize_single_chunk(chunk)
        if summary_body:
            section_breakdowns.append((chunk.title, summary_body))

    # 5. Conclusion & Outcomes (Directly derived from the final sections/chunks)
    terminal_chunks = [c for c in chunks if c.is_terminal] or [chunks[-1]] if chunks else []
    conclusion_text = terminal_chunks[-1].text if terminal_chunks else full_text[-1200:]
    conclusion_sentences = score_and_extract_key_sentences(conclusion_text, max_sentences=2)
    conclusion_paragraph = " ".join(conclusion_sentences) if conclusion_sentences else "Document analysis and outcomes successfully processed."

    # Build the Markdown Document
    md_lines: List[str] = [
        f"# Document Summary: {doc_title}",
        "",
        "## Overview",
        overview_paragraph,
        "",
        "## Key Points",
    ]
    for pt in key_points:
        md_lines.append(f"- {pt}")
    md_lines.append("")

    if metrics_and_dates:
        md_lines.append("## Important Findings & Metrics")
        for finding in metrics_and_dates[:6]:
            md_lines.append(f"- **Key Detail**: {finding}")
        md_lines.append("")

    if len(section_breakdowns) > 1:
        md_lines.append("## Section Highlights")
        for title, s_sum in section_breakdowns:
            md_lines.append(f"- **{title}**: {s_sum}")
        md_lines.append("")

    md_lines.append("## Conclusion")
    md_lines.append(conclusion_paragraph)

    final_markdown = "\n".join(md_lines).strip()
    elapsed_sec = round(time.time() - start_time, 2)

    return {
        "summary": final_markdown,
        "format": "markdown",
        "engine": "hierarchical_summarizer",
        "chunks_processed": len(chunks),
        "characters_read": original_char_count,
        "elapsed_seconds": elapsed_sec,
        "key_points": key_points,
        "source": "whole document",
        "message": f"Summarized entire document across {len(chunks)} section(s) in {elapsed_sec}s.",
    }


def generate_complete_document_summary(
    text: str,
    doc_title: str = "Document",
    length_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Public entry point: processes the ENTIRE document from start to end.
    
    Guarantees that later sections participate in the final summary and no content
    is silently dropped. Returns clean, structured Markdown.
    """
    start_time = time.time()
    raw_text = (text or "").strip()
    original_char_count = len(raw_text)

    # 1. Clean prose while retaining substantive content
    cleaned = clean_prose(raw_text)
    if not cleaned or len(cleaned) < 30:
        logger.warning("Document summarizer received text with no readable prose (chars=%d).", original_char_count)
        return {
            "summary": None,
            "format": "markdown",
            "engine": "none",
            "chunks_processed": 0,
            "characters_read": original_char_count,
            "key_points": [],
            "source": "whole document",
            "message": "No readable text could be extracted from this document to summarize.",
        }

    # 2. Partition into complete semantic chunks
    chunks = create_chunks_for_document(cleaned)
    logger.info(
        "Hierarchical Summarizer: original_len=%d, cleaned_len=%d, chunks_created=%d",
        original_char_count, len(cleaned), len(chunks)
    )

    # 3. Map Phase: Summarize every chunk
    for c in chunks:
        c.intermediate_summary = summarize_single_chunk(c)

    # 4. Reduce Phase: Synthesize global Markdown summary
    result = synthesize_markdown_summary(
        doc_title=doc_title,
        chunks=chunks,
        full_text=cleaned,
        original_char_count=original_char_count,
        start_time=start_time,
    )

    logger.info(
        "Hierarchical Summarizer complete: chunks=%d, result_len=%d, time=%.2fs",
        result["chunks_processed"], len(result["summary"] or ""), result["elapsed_seconds"]
    )
    return result

