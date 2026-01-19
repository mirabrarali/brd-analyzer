import io
import os
import re
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from groq import Groq
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from docx import Document

app = FastAPI()


def _extract_text_from_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        if txt.strip():
            parts.append(txt)
    return "\n\n".join(parts).strip()


def _extract_text_from_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = []
    for p in doc.paragraphs:
        if p.text and p.text.strip():
            parts.append(p.text)
    return "\n".join(parts).strip()


def _call_groq_brd_agent(document_text: str) -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GROQ_API_KEY")

    client = Groq(api_key=api_key)

    system = (
        "You are a senior Business Analyst with 15+ years of experience writing professional "
        "Business Requirements Documents for enterprise clients including banks and financial institutions. "
        "Your analysis must read as if written by a domain expert who deeply understands the business process, "
        "not as a simple extraction of labels from diagrams. Provide insightful analysis, identify gaps, "
        "and offer strategic recommendations. Output MUST be valid JSON only."
    )

    user = (
        "Analyze the following BRD / process document and produce a comprehensive, professional report.\n\n"
        "Return JSON only with this exact schema (all keys required, arrays can be empty):\n"
        "{\n"
        '  "title": "string (professional report title)",\n'
        '  "concise_summary": "string (2-3 paragraph executive summary, 200-300 words, written in professional prose)",\n'
        '  "business_objectives": ["string (each objective as a complete sentence)"],\n'
        '  "in_scope": ["string"],\n'
        '  "out_of_scope": ["string"],\n'
        '  "stakeholders_and_roles": ["string (format: Role - responsibilities description)"],\n'
        '  "current_process": ["string (describe each step in detail)"],\n'
        '  "proposed_process": ["string (describe improvements and changes)"],\n'
        '  "functional_requirements": ["string (format: FR-001: Requirement description [Priority: Must/Should/Could])"],\n'
        '  "non_functional_requirements": ["string (format: NFR-001: Requirement description)"],\n'
        '  "data_entities": ["string (format: Entity Name - description and purpose)"],\n'
        '  "integrations": ["string (format: System Name (Direction) - integration description)"],\n'
        '  "assumptions": ["string"],\n'
        '  "dependencies": ["string"],\n'
        '  "risks": ["string (format: Risk description | Impact: High/Medium/Low | Mitigation: strategy)"],\n'
        '  "gaps_and_questions": ["string"],\n'
        '  "process_flow_analysis": ["string (detailed analysis of the workflow, decision points, and swimlane interactions)"],\n'
        '  "suggestions": ["string (strategic recommendations with rationale)"],\n'
        '  "preferred_steps": ["string (numbered implementation steps with timeline considerations)"],\n'
        '  "acceptance_criteria": ["string"],\n'
        '  "test_scenarios": ["string (format: TS-001: Test scenario description)"]\n'
        "}\n\n"
        "IMPORTANT RULES:\n"
        "- Write as a senior analyst, not as an AI. Use professional business language.\n"
        "- The concise_summary MUST be written as flowing paragraphs, NOT bullet points.\n"
        "- Do NOT just extract labels from diagrams. Analyze the business logic and provide insights.\n"
        "- All list items must be plain strings (no nested objects).\n"
        "- Include at least 15 functional requirements and 8 test scenarios.\n"
        "- Provide strategic suggestions that demonstrate domain expertise.\n"
        "- If information is missing, note it in gaps_and_questions with specific questions.\n\n"
        "DOCUMENT CONTENT:\n"
        f"{document_text[:100000]}"
    )

    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=4096,
    )

    content = resp.choices[0].message.content or ""
    import json

    try:
        return json.loads(content)
    except Exception:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = content[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        preview = re.sub(r"\s+", " ", content).strip()[:500]
        raise HTTPException(
            status_code=502,
            detail=f"Model returned non-JSON output. Preview: {preview}",
        )


def _para(text: str, style: ParagraphStyle) -> Paragraph:
    safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = safe.replace("\n", "<br/>")
    return Paragraph(safe, style)


def _build_pdf(report: Dict[str, Any]) -> bytes:
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=str(report.get("title") or "BRD Analysis Report"),
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        spaceAfter=20,
        textColor="#1a365d",
    )
    h2 = ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        spaceBefore=14,
        spaceAfter=8,
        textColor="#2c5282",
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    bullet = ParagraphStyle(
        "Bullet",
        parent=body,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=3,
    )

    story = []

    story.append(_para(str(report.get("title") or "BRD Analysis Report"), h1))
    story.append(Spacer(1, 8))

    def _format_dict_item(d: dict) -> str:
        parts = []
        for k, v in d.items():
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            parts.append(f"{k}: {v}")
        return " | ".join(parts)

    def section(title: str, content: Any, as_paragraph: bool = False):
        story.append(_para(title, h2))
        story.append(Spacer(1, 4))
        if content is None or content == "" or content == []:
            story.append(_para("Not specified.", body))
        elif isinstance(content, str):
            story.append(_para(content, body))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = _format_dict_item(item)
                else:
                    text = str(item)
                story.append(_para(f"\u2022 {text}", bullet))
        elif isinstance(content, dict):
            for k, v in content.items():
                if isinstance(v, list):
                    story.append(_para(f"{k}:", body))
                    for sub in v:
                        if isinstance(sub, dict):
                            story.append(_para(f"  \u2022 {_format_dict_item(sub)}", bullet))
                        else:
                            story.append(_para(f"  \u2022 {sub}", bullet))
                else:
                    story.append(_para(f"{k}: {v}", body))
        else:
            story.append(_para(str(content), body))
        story.append(Spacer(1, 6))

    section("Executive Summary", report.get("concise_summary"), as_paragraph=True)
    section("Business Objectives", report.get("business_objectives"))
    section("In Scope", report.get("in_scope"))
    section("Out of Scope", report.get("out_of_scope"))
    section("Stakeholders and Roles", report.get("stakeholders_and_roles"))

    story.append(PageBreak())

    section("Current Process", report.get("current_process"))
    section("Proposed Process", report.get("proposed_process"))
    section("Functional Requirements", report.get("functional_requirements"))
    section("Non-Functional Requirements", report.get("non_functional_requirements"))
    section("Data Entities", report.get("data_entities"))
    section("System Integrations", report.get("integrations"))
    section("Assumptions", report.get("assumptions"))
    section("Dependencies", report.get("dependencies"))
    section("Risk Assessment", report.get("risks"))

    story.append(PageBreak())

    section("Gaps and Open Questions", report.get("gaps_and_questions"))
    section("Process Flow Analysis", report.get("process_flow_analysis"))
    section("Strategic Recommendations", report.get("suggestions"))
    section("Implementation Roadmap", report.get("preferred_steps"))
    section("Acceptance Criteria", report.get("acceptance_criteria"))
    section("Test Scenarios", report.get("test_scenarios"))

    doc.build(story)
    return buf.getvalue()


@app.get("/health")
@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    output: str = Query("pdf", pattern="^(pdf|json)$"),
) -> Any:
    filename = file.filename or "document"
    ext = (filename.split(".")[-1] if "." in filename else "").lower()
    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    if ext == "pdf":
        text = _extract_text_from_pdf(data)
    elif ext == "docx":
        text = _extract_text_from_docx(data)
    else:
        raise HTTPException(status_code=400, detail="Only .pdf or .docx supported")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found in document")

    report = _call_groq_brd_agent(text)

    if output == "json":
        return JSONResponse(report)

    pdf_bytes = _build_pdf(report)
    out_name = (os.path.splitext(filename)[0] or "brd-report") + "-brd-report.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{out_name}\"",
            "Cache-Control": "no-store",
        },
    )
