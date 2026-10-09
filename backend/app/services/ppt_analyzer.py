"""Document Analysis & Presentation Synthesis Engine for RapidDoc.

Analyzes document structure, domain, quantitative metrics, workflows, comparisons,
and key conclusions first, then synthesizes a presentation with purposeful,
tailored slide layouts rather than generic walls of bullets.
"""

import io
import json
import logging
import re
from typing import List, Dict, Any, Optional

from RapidDoc.backend.app.config import settings

logger = logging.getLogger(__name__)

# Metric detection patterns
_METRIC_RE = re.compile(
    r"\b(\$?\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?\s*(?:billion|million|k|M|B)?|\b\d+(?:\.\d+)?x\b|\b\d{1,3}(?:,\d{3})+\+?|\b\d+(?:\.\d+)?\s*(?:ms|sec|seconds|fps|GB|TB|users|clients|nodes))\b",
    re.IGNORECASE,
)

# Step / Phase detection
_STEP_RE = re.compile(
    r"\b(?:step|phase|stage|milestone|module)\s*([0-9A-Za-z]+)[:\s–—]+([^\n\.;]+)",
    re.IGNORECASE,
)

# Comparison cues
_COMPARE_RE = re.compile(
    r"\b(?:vs\.?|versus|problem\s+vs\s+solution|challenges?\s+(?:vs|and)\s+solutions?|pros\s+and\s+cons|advantages|before\s+and\s+after|current\s+state\s+vs\s+future\s+state)\b",
    re.IGNORECASE,
)

# Conclusion / Takeaways cues
_TAKEAWAY_RE = re.compile(
    r"\b(?:conclusion|key\s+takeaways?|summary|recommendations?|next\s+steps?|future\s+work|closing\s+remarks?)\b",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def extract_document_text_and_structure(items: list) -> dict:
    """Analyze the raw items from DOCX or PDF into a structured document representation."""
    full_text_parts = []
    headings = []
    paragraphs = []
    tables = []
    code_blocks = []
    image_pages = []

    for item in items:
        kind = item.get("kind")
        text = _clean_text(item.get("text") or "")

        if kind == "paragraph":
            level = item.get("heading_level") or 0
            if text:
                full_text_parts.append(text)
                if 1 <= level <= 3:
                    headings.append({
                        "text": text,
                        "level": level,
                        "index": item.get("index"),
                        "page": item.get("source_page"),
                    })
                else:
                    paragraphs.append({
                        "text": text,
                        "index": item.get("index"),
                        "page": item.get("source_page"),
                    })
        elif kind == "table":
            rows = item.get("rows") or []
            if rows:
                tables.append({"rows": rows, "page": item.get("source_page")})
        elif kind == "image_page":
            image_pages.append(item)

    raw_text = "\n\n".join(full_text_parts)

    # Infer document title
    doc_title = ""
    subtitle = ""
    if headings:
        doc_title = headings[0]["text"]
        if len(paragraphs) > 0 and len(paragraphs[0]["text"]) < 120:
            subtitle = paragraphs[0]["text"]
    elif paragraphs:
        first_line = paragraphs[0]["text"].split("\n")[0].strip()
        doc_title = first_line[:90] if len(first_line) > 5 else "Document Presentation"
        if len(paragraphs) > 1 and len(paragraphs[1]["text"]) < 120:
            subtitle = paragraphs[1]["text"]

    return {
        "title": doc_title or "Executive Overview",
        "subtitle": subtitle,
        "raw_text": raw_text,
        "headings": headings,
        "paragraphs": paragraphs,
        "tables": tables,
        "image_pages": image_pages,
    }


def analyze_document_with_ai(extracted: dict) -> Optional[List[Dict[str, Any]]]:
    """Use Gemini to deeply analyze document and return tailored slide specifications."""
    api_key = (settings.GEMINI_API_KEY or "").strip()
    if not api_key or api_key in ("YOUR_GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE"):
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            settings.GEMINI_MODEL,
            generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
        )

        doc_summary_input = extracted["raw_text"][:8000]
        if not doc_summary_input.strip():
            return None

        prompt = f"""You are an executive presentation architect and slide designer.
Analyze this document thoroughly and produce a cohesive, professional slide deck outline (6 to 9 slides).

CRITICAL REQUIREMENT:
DO NOT generate generic random slides or repeat "Overview".
Each slide must have an INTENTIONAL layout matching its specific role in the narrative:

Available Slide Layouts:
1. "title": Presentation title, subtitle, category badge.
   Attributes: {{"layout": "title", "title": "...", "subtitle": "...", "category": "..."}}

2. "summary_cards": Executive summary or problem context with 2-3 structured cards.
   Attributes: {{"layout": "summary_cards", "title": "Executive Summary", "cards": [{{"title": "...", "text": "..."}}]}}

3. "metrics": Quantitative results, benchmarks, KPIs (2 to 4 highlight stats).
   Only use if document contains numerical data, percentages, metrics, or revenue.
   Attributes: {{"layout": "metrics", "title": "Key Metrics & Results", "metrics": [{{"number": "98.5%", "label": "...", "desc": "..."}}]}}

4. "two_column": Comparative analysis, Problem vs Solution, or Key Pillars.
   Attributes: {{"layout": "two_column", "title": "...", "col1_title": "...", "col1_bullets": ["..."], "col2_title": "...", "col2_bullets": ["..."]}}

5. "steps": Sequential process, workflow, implementation phases, or methodology (3 to 4 steps).
   Attributes: {{"layout": "steps", "title": "...", "steps": [{{"step": "01", "title": "...", "desc": "..."}}]}}

6. "bullets": High-impact key points (3 to 5 concise bullets). Keep text punchy, not long paragraphs.
   Attributes: {{"layout": "bullets", "title": "...", "bullets": [{{"text": "..."}}]}}

7. "takeaways": Strategic conclusions, recommendations, and next steps (3 to 4 takeaways).
   Attributes: {{"layout": "takeaways", "title": "Key Takeaways & Conclusion", "takeaways": [{{"title": "...", "desc": "..."}}]}}

Document Content:
---
{doc_summary_input}
---

Return a valid JSON array of slide specifications. Ensure every slide title is descriptive and meaningful."""

        response = model.generate_content(prompt)
        content = (response.text or "").strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        slides = json.loads(content)
        if isinstance(slides, list) and len(slides) >= 3:
            logger.info("Successfully synthesized %d slides using Gemini presentation analyzer", len(slides))
            return slides
    except Exception as exc:
        logger.warning("AI document presentation analysis failed or rate limited (%s), using intelligent heuristic analyzer", exc)

    return None


def _extract_metrics_heuristically(text: str) -> List[Dict[str, str]]:
    """Scan text for high-impact quantifiable metrics and statistics."""
    metrics = []
    seen_numbers = set()

    for line in text.split("\n"):
        line = line.strip()
        for match in _METRIC_RE.finditer(line):
            num = match.group(1).strip()
            if num in seen_numbers:
                continue
            seen_numbers.add(num)

            # Determine label and context from nearby sentence words
            words = [w for w in re.split(r"[\s,;]+", line) if w and w != num]
            label = " ".join(words[:4]).strip().title() if words else "Verified Metric"
            desc = line[:90] if len(line) > len(label) else "Document finding"

            metrics.append({
                "number": num,
                "label": label[:32] or "Key Indicator",
                "desc": desc,
            })
            if len(metrics) >= 4:
                return metrics
    return metrics


def _extract_steps_heuristically(paragraphs: list) -> List[Dict[str, str]]:
    """Detect methodology, workflow, or pipeline steps in the document."""
    steps = []
    step_num = 1

    for p in paragraphs:
        text = p["text"]
        m = _STEP_RE.search(text)
        if m:
            s_name = m.group(1).strip()
            s_title = m.group(2).strip().title()
            # Desc is the remainder of paragraph
            desc = text[m.end():].strip().lstrip(":- ")
            if not desc:
                desc = s_title
            steps.append({
                "step": f"{step_num:02d}",
                "title": s_title[:40] or f"Phase {step_num}",
                "desc": desc[:110] or "Implementation milestone",
            })
            step_num += 1
            if len(steps) >= 4:
                break
        elif re.search(r"^\s*(?:1\.|first|step\s*1)\b", text, re.I) and len(steps) == 0:
            sentences = [s.strip() for s in text.split(".") if s.strip()]
            for idx, s in enumerate(sentences[:4], start=1):
                steps.append({
                    "step": f"{idx:02d}",
                    "title": f"Phase {idx}",
                    "desc": s[:110],
                })
            break

    return steps


def analyze_document_heuristically(extracted: dict, items: list) -> List[Dict[str, Any]]:
    """Deep heuristic semantic analyzer: creates tailored, structured slides based on content roles."""
    slides = []
    title = extracted.get("title") or "Executive Presentation"
    subtitle = extracted.get("subtitle") or "Comprehensive Document Analysis"
    raw_text = extracted.get("raw_text") or ""
    paragraphs = extracted.get("paragraphs") or []
    headings = extracted.get("headings") or []
    tables = extracted.get("tables") or []

    # 1. Title Slide
    slides.append({
        "layout": "title",
        "title": title,
        "subtitle": subtitle,
        "bullets": [{"text": subtitle}] if subtitle else [],
    })

    # 2. Executive Summary / Context Slide (summary_cards)
    summary_paras = [p["text"] for p in paragraphs[:3] if len(p["text"]) > 20]
    if summary_paras:
        cards = []
        labels = ["Core Objective", "Context & Scope", "Key Focus Area"]
        for idx, text in enumerate(summary_paras[:3]):
            card_title = labels[idx] if idx < len(labels) else f"Pillar {idx + 1}"
            cards.append({
                "title": card_title,
                "text": text[:140],
            })
        slides.append({
            "layout": "summary_cards",
            "title": "Executive Summary & Core Objectives",
            "cards": cards,
            "source_paragraphs": frozenset(p.get("index") for p in paragraphs[:3] if p.get("index") is not None),
        })

    # 3. Quantitative Metrics Slide (metrics) if 2 or more metrics exist
    metrics = _extract_metrics_heuristically(raw_text)
    if len(metrics) >= 2:
        slides.append({
            "layout": "metrics",
            "title": "Key Metrics & Quantifiable Results",
            "metrics": metrics,
        })

    # 4. Steps / Methodology / Pipeline Slide (steps)
    steps = _extract_steps_heuristically(paragraphs)
    if len(steps) >= 2:
        slides.append({
            "layout": "steps",
            "title": "Methodology & Execution Pipeline",
            "steps": steps,
        })

    # 5. Comparative Analysis / Two-Column Slide (two_column)
    compare_found = False
    for p in paragraphs:
        if _COMPARE_RE.search(p["text"]):
            sentences = [s.strip() for s in p["text"].split(".") if len(s.strip()) > 15]
            if len(sentences) >= 2:
                mid = len(sentences) // 2
                slides.append({
                    "layout": "two_column",
                    "title": "Comparative Analysis & Evaluation",
                    "col1_title": "Current State & Challenges",
                    "col1_bullets": sentences[:mid],
                    "col2_title": "Proposed Solution & Impact",
                    "col2_bullets": sentences[mid:mid + 3],
                    "source_paragraphs": frozenset({p.get("index")}) if p.get("index") else frozenset(),
                })
                compare_found = True
                break

    # 6. Structured Tables
    for tbl in tables[:2]:
        rows = tbl.get("rows") or []
        if len(rows) >= 2:
            slides.append({
                "layout": "table",
                "title": "Data Overview & Specifications",
                "table": {"rows": rows},
                "source_page": tbl.get("page"),
            })

    # 7. Topic-Specific Content Slides from Headings / Paragraphs
    if headings:
        for h in headings[1:4]:
            h_text = h["text"]
            # Find paragraphs under this heading
            h_idx = h.get("index") or 0
            matching_paras = [
                p["text"] for p in paragraphs
                if p.get("index") is not None and abs(p["index"] - h_idx) <= 5
            ]
            if not matching_paras:
                matching_paras = [p["text"] for p in paragraphs[:2]]
            
            bullets = []
            for mp in matching_paras[:3]:
                # Split into short punchy presentation points
                for sentence in mp.split("."):
                    sentence = _clean_text(sentence)
                    if len(sentence) >= 15:
                        bullets.append({"text": sentence[:110], "level": 0})
                        if len(bullets) >= 4:
                            break
                if len(bullets) >= 4:
                    break

            if bullets:
                slides.append({
                    "layout": "bullets",
                    "title": h_text,
                    "bullets": bullets,
                    "source_page": h.get("page"),
                    "source_paragraphs": frozenset({h_idx}),
                })
    else:
        # Generate a structured deep dive slide
        body_bullets = []
        for p in paragraphs[3:7]:
            for sent in p["text"].split("."):
                sent = _clean_text(sent)
                if len(sent) >= 20:
                    body_bullets.append({"text": sent[:110], "level": 0})
                    if len(body_bullets) >= 4:
                        break
            if len(body_bullets) >= 4:
                break
        if body_bullets:
            slides.append({
                "layout": "bullets",
                "title": "Detailed Findings & Analysis",
                "bullets": body_bullets,
            })

    # 8. Key Takeaways & Strategic Conclusion (takeaways)
    takeaway_candidates = []
    # Search near the end of the document
    for p in reversed(paragraphs[-4:]):
        for sent in p["text"].split("."):
            sent = _clean_text(sent)
            if len(sent) >= 20:
                takeaway_candidates.append(sent[:120])
                if len(takeaway_candidates) >= 3:
                    break
        if len(takeaway_candidates) >= 3:
            break

    if not takeaway_candidates and paragraphs:
        takeaway_candidates = [p["text"][:120] for p in paragraphs[-3:]]

    if takeaway_candidates:
        takeaway_items = []
        headers = ["Strategic Value", "Operational Impact", "Key Recommendation"]
        for idx, text in enumerate(takeaway_candidates[:3]):
            h_label = headers[idx] if idx < len(headers) else f"Action Point {idx + 1}"
            takeaway_items.append({"title": h_label, "desc": text})
        slides.append({
            "layout": "takeaways",
            "title": "Key Takeaways & Strategic Next Steps",
            "takeaways": takeaway_items,
        })

    return slides


def analyze_and_build_outline(items: list) -> List[Dict[str, Any]]:
    """Main Entry Point: Analyzes document first, then builds an intentional, tailored presentation."""
    extracted = extract_document_text_and_structure(items)

    # 1. Try AI-powered deep semantic presentation synthesis
    ai_slides = analyze_document_with_ai(extracted)
    if ai_slides and len(ai_slides) >= 3:
        # Standardize slide specs and preserve source page mapping for images
        for idx, s in enumerate(ai_slides):
            if "source_page" not in s and items:
                # Distribute source pages so pictures can attach
                s["source_page"] = min(idx, max(0, len(items) - 1))
        return ai_slides

    # 2. Intelligent heuristic analyzer fallback
    return analyze_document_heuristically(extracted, items)
