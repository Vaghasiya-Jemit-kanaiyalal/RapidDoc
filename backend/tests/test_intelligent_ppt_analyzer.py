import io
import pytest
from pptx import Presentation

from RapidDoc.backend.app.services.ppt_analyzer import (
    extract_document_text_and_structure,
    analyze_document_heuristically,
    analyze_and_build_outline,
    _extract_metrics_heuristically,
    _extract_steps_heuristically,
)
from RapidDoc.backend.app.services.ppt_templates import render_deck, build_outline


def test_metric_extraction_and_metrics_slide():
    doc_text = """
    Financial Performance & Q3 Results
    In Q3, our cloud platform achieved a 99.8% uptime SLA.
    Total annual revenue expanded to $4.2M, representing a 3.5x increase year over year.
    We successfully served over 50,000 active clients across 12 regions with latency under 45ms.
    """
    metrics = _extract_metrics_heuristically(doc_text)
    assert len(metrics) >= 2
    # Verify numbers extracted
    nums = [m["number"] for m in metrics]
    assert any("99.8%" in n or "$4.2M" in n or "3.5x" in n or "50,000" in n for n in nums)

    items = [
        {"kind": "paragraph", "heading_level": 1, "text": "Financial Performance & Q3 Results", "index": 0},
        {"kind": "paragraph", "heading_level": 0, "text": "In Q3, our cloud platform achieved a 99.8% uptime SLA.", "index": 1},
        {"kind": "paragraph", "heading_level": 0, "text": "Total annual revenue expanded to $4.2M, representing a 3.5x increase.", "index": 2},
        {"kind": "paragraph", "heading_level": 0, "text": "We served over 50,000 active clients with latency under 45ms.", "index": 3},
    ]
    slides = build_outline(items)
    layouts = [s["layout"] for s in slides]
    assert "metrics" in layouts

    # Render presentation deck with modern theme
    prs = render_deck(slides, theme="modern")
    assert len(prs.slides) >= 3


def test_steps_workflow_extraction_and_steps_slide():
    items = [
        {"kind": "paragraph", "heading_level": 1, "text": "Deployment Pipeline Architecture", "index": 0},
        {"kind": "paragraph", "heading_level": 0, "text": "Phase 1: Code Ingestion and automated static security analysis.", "index": 1},
        {"kind": "paragraph", "heading_level": 0, "text": "Phase 2: Container Compilation and multi-stage Docker builds.", "index": 2},
        {"kind": "paragraph", "heading_level": 0, "text": "Phase 3: Production Rollout with blue-green traffic switching.", "index": 3},
    ]
    slides = build_outline(items)
    layouts = [s["layout"] for s in slides]
    assert "steps" in layouts

    # Find the steps slide
    step_slide = next(s for s in slides if s["layout"] == "steps")
    assert len(step_slide.get("steps", [])) >= 3
    assert step_slide["steps"][0]["step"] == "01"

    prs = render_deck(slides, theme="corporate")
    assert len(prs.slides) >= 3


def test_comparative_analysis_and_two_column_slide():
    items = [
        {"kind": "paragraph", "heading_level": 1, "text": "Microservices vs Monolithic Architecture", "index": 0},
        {"kind": "paragraph", "heading_level": 0, "text": "Current Monolith vs Modern Microservices. The monolithic system suffered from tight coupling and slow deployment cycles. Modern microservices allow independent scaling and fault tolerance across micro-components.", "index": 1},
        {"kind": "paragraph", "heading_level": 0, "text": "Key Takeaways: Adopt distributed tracing and containerization to achieve resiliency.", "index": 2},
    ]
    slides = build_outline(items)
    layouts = [s["layout"] for s in slides]
    assert "two_column" in layouts

    two_col = next(s for s in slides if s["layout"] == "two_column")
    assert two_col.get("col1_title") is not None
    assert two_col.get("col2_title") is not None

    prs = render_deck(slides, theme="minimal")
    assert len(prs.slides) >= 3


def test_executive_summary_and_takeaways_slides():
    items = [
        {"kind": "paragraph", "heading_level": 1, "text": "Healthcare AI Diagnostic Report", "index": 0},
        {"kind": "paragraph", "heading_level": 0, "text": "This study evaluates the deep learning diagnostic assistant across 14 hospital networks.", "index": 1},
        {"kind": "paragraph", "heading_level": 0, "text": "Our primary objective is decreasing diagnostic turnaround time while maintaining accuracy.", "index": 2},
        {"kind": "paragraph", "heading_level": 0, "text": "The framework integrates HIPAA-compliant federated learning protocols.", "index": 3},
        {"kind": "paragraph", "heading_level": 0, "text": "Conclusion and recommendations: The model showed exceptional stability in clinical trials and is recommended for staged emergency rollout.", "index": 4},
    ]
    slides = build_outline(items)
    layouts = [s["layout"] for s in slides]
    # Verify summary cards and takeaways were purposefully created
    assert "summary_cards" in layouts
    assert "takeaways" in layouts

    prs = render_deck(slides, theme="modern")
    buf = io.BytesIO()
    prs.save(buf)
    data = buf.getvalue()
    assert data[:2] == b"PK"
    reloaded = Presentation(io.BytesIO(data))
    assert len(reloaded.slides) == len(slides)


def test_all_custom_slides_fit_within_slide_geometry():
    """Verify that none of the new layout shapes exceed 16:9 slide boundaries."""
    custom_slides = [
        {"layout": "title", "title": "Comprehensive AI Platform", "subtitle": "Enterprise Solution Overview"},
        {
            "layout": "summary_cards",
            "title": "Executive Summary",
            "cards": [
                {"title": "Core Objective", "text": "Deploy scalable natural language understanding models."},
                {"title": "Architecture", "text": "Microservices with automated failover and caching."},
                {"title": "Expected Impact", "text": "40% reduction in response latency for end users."},
            ],
        },
        {
            "layout": "metrics",
            "title": "Performance Benchmarks",
            "metrics": [
                {"number": "99.9%", "label": "Uptime", "desc": "Continuous production operation"},
                {"number": "4.5x", "label": "Throughput", "desc": "Compared to legacy pipeline"},
                {"number": "12ms", "label": "Latency", "desc": "Sub-millisecond API response"},
                {"number": "$2.1M", "label": "Cost Savings", "desc": "Estimated annual cloud savings"},
            ],
        },
        {
            "layout": "two_column",
            "title": "Strategic Evaluation",
            "col1_title": "Existing Challenges",
            "col1_bullets": ["Fragmented data silos", "Manual review bottlenecks", "High latency"],
            "col2_title": "Proposed Solution",
            "col2_bullets": ["Centralized vector retrieval", "Automated validation", "Sub-second processing"],
        },
        {
            "layout": "steps",
            "title": "Rollout Roadmap",
            "steps": [
                {"step": "01", "title": "Discovery", "desc": "Audit data pipelines and requirements"},
                {"step": "02", "title": "Model Training", "desc": "Fine-tune models on domain data"},
                {"step": "03", "title": "Staging Validation", "desc": "Validate accuracy and security"},
                {"step": "04", "title": "Production Launch", "desc": "Deploy across regional clusters"},
            ],
        },
        {
            "layout": "takeaways",
            "title": "Key Recommendations",
            "takeaways": [
                {"title": "Strategic Recommendation", "desc": "Adopt microservices architecture."},
                {"title": "Operational Impact", "desc": "Eliminate manual data bottlenecks."},
                {"title": "Timeline", "desc": "Complete Phase 1 within 6 weeks."},
            ],
        },
    ]

    for theme_name in ("modern", "corporate", "minimal"):
        prs = render_deck(custom_slides, theme=theme_name)
        sw = prs.slide_width
        sh = prs.slide_height

        for slide_no, slide in enumerate(prs.slides, 1):
            for shape in slide.shapes:
                try:
                    left, top, width, height = shape.left, shape.top, shape.width, shape.height
                except Exception:
                    continue
                if None in (left, top, width, height):
                    continue
                # Shape must fit within slide boundaries
                assert left >= 0, f"Slide {slide_no} shape left < 0: {left}"
                assert top >= 0, f"Slide {slide_no} shape top < 0: {top}"
                assert (left + width) <= sw + 10000, f"Slide {slide_no} shape width exceeds slide: {left + width} > {sw}"
                assert (top + height) <= sh + 10000, f"Slide {slide_no} shape height exceeds slide: {top + height} > {sh}"
