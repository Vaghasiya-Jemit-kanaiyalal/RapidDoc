"""End-to-End Tests for RapidDoc Hierarchical Long-Document Summarizer.

Validates that:
  1. The complete document participates in the summary (no silent truncation).
  2. Late-section facts (e.g. from the final 10% of the document) are retained.
  3. Output is valid, structured Markdown (# Overview, ## Key Points, ## Conclusion).
  4. Exports to both .md and .txt work cleanly.
"""

import pytest
from RapidDoc.backend.app.services.document_summarizer import (
    create_chunks_for_document,
    generate_complete_document_summary,
    segment_document_into_sections,
)
from RapidDoc.backend.app.services.summary_export import (
    build_summary_bytes,
    build_summary_md,
    build_summary_txt,
)


@pytest.fixture
def multi_section_long_doc():
    return """
# Project Titan: Autonomous Fleet Telemetry Architecture

## 1. Executive Summary & Goals
Project Titan deployed next-generation telemetry collectors across 5,000 autonomous vehicles in Q3 2026. Prior telemetry ingestion suffered from 12% packet loss during peak highway commute hours.

## 2. Distributed Sensor Mesh
The sensor network gathers LiDAR, radar, camera frame hashes, and tire-pressure sensor packets. Ingestion throughput averages 48,000 data frames per second across 8 edge ingestion regions.

## 3. High-Throughput Edge Ingestion
Edge nodes execute lightweight schema validation and temporal deduplication. Compressed event streams are buffered in local NVMe storage arrays before TLS replication to central data lakes.

## 4. Network Optimization & Resilience
Using UDP forward error correction combined with dynamic TCP fallback reduced packet loss from 12% down to 0.04%. Total monthly bandwidth consumption dropped by 38% through delta compression.

## 5. Security & Cryptographic Integrity
Every telemetry frame is signed with an elliptic curve signature (Ed25519) on the vehicle's hardware security module (HSM). Replay attacks are rejected using monotonically increasing nanosecond sequence counters.

## 6. Critical Late Finding & Production Outcomes
During final stress audits on October 4, 2026, the telemetry pipeline sustained 120,000 frames per second with zero message loss. Total fleet operating cost was reduced by $1.85M annually, and sensor synchronization latency dropped to 4.2ms.
"""


def test_complete_document_all_sections_chunked(multi_section_long_doc):
    chunks = create_chunks_for_document(multi_section_long_doc)
    assert len(chunks) >= 4, f"Expected at least 4 chunks, got {len(chunks)}"
    # Verify first and last sections are present
    assert any("Executive" in c.title or "Goals" in c.title for c in chunks)
    assert any("Critical Late Finding" in c.title or "Outcome" in c.title for c in chunks)


def test_late_section_facts_retained_in_summary(multi_section_long_doc):
    result = generate_complete_document_summary(multi_section_long_doc, doc_title="Project Titan")
    summary = result["summary"]

    assert summary is not None
    assert summary.startswith("# Document Summary: Project Titan")
    assert "## Overview" in summary
    assert "## Key Points" in summary
    assert "## Conclusion" in summary

    # Critical late-section facts (from Section 6) MUST appear in the summary
    assert any(term in summary for term in ["120,000", "$1.85M", "4.2ms", "October 4", "zero message loss"]), (
        "Late-section information was dropped! The model failed to summarize the whole document."
    )


def test_no_silent_truncation_metric_reporting(multi_section_long_doc):
    result = generate_complete_document_summary(multi_section_long_doc, doc_title="Project Titan")
    assert result["chunks_processed"] >= 4
    assert result["characters_read"] == len(multi_section_long_doc.strip())
    assert result["format"] == "markdown"
    assert result["engine"] == "hierarchical_summarizer"


def test_md_and_txt_export_complete_integrity(multi_section_long_doc):
    result = generate_complete_document_summary(multi_section_long_doc, doc_title="Project Titan")
    payload = {
        "summary": result["summary"],
        "key_points": result["key_points"],
        "source": "whole document",
        "engine": result["engine"],
        "characters": result["characters_read"],
    }

    # 1. Test .md export
    md_bytes, md_name, md_mime = build_summary_bytes("md", payload, "Project Titan")
    assert md_mime == "text/markdown; charset=utf-8"
    assert md_name == "Project_Titan.md"
    md_text = md_bytes.decode("utf-8")
    assert md_text.startswith("# Document Summary: Project Titan")
    assert "## Key Points" in md_text

    # 2. Test .txt export (clean plain text without raw markdown tags)
    txt_bytes, txt_name, txt_mime = build_summary_bytes("txt", payload, "Project Titan")
    assert txt_mime == "text/plain; charset=utf-8"
    assert txt_name == "Project_Titan.txt"
    txt_text = txt_bytes.decode("utf-8")
    assert "**" not in txt_text
    assert "#" not in txt_text
    assert "PROJECT TITAN" in txt_text
