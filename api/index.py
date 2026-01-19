import io
import os
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
        "You are a BRD Analyzer Agent. Produce a structured business requirements analysis "
        "based on the provided document content. Be concise but complete. "
        "Output MUST be valid JSON only, with the schema described in the user message."
    )

    schema = {
        "title": "string",
        "concise_summary": "string (8-14 bullets OR ~150-250 words)",
        "business_objectives": ["string"],
        "in_scope": ["string"],
        "out_of_scope": ["string"],
        "stakeholders_and_roles": [{"role": "string", "responsibilities": ["string"]}],
        "current_process": ["string"],
        "proposed_process": ["string"],
        "functional_requirements": [{"id": "FR-#", "requirement": "string", "priority": "Must/Should/Could"}],
        "non_functional_requirements": [{"id": "NFR-#", "requirement": "string"}],
        "data_entities": [{"name": "string", "notes": "string"}],
        "integrations": [{"system": "string", "direction": "inbound/outbound/both", "notes": "string"}],
        "assumptions": ["string"],
        "dependencies": ["string"],
        "risks": [{"risk": "string", "impact": "Low/Med/High", "mitigation": "string"}],
        "gaps_and_questions": ["string"],
        "diagrams_and_notes": ["string (describe swimlanes/flows and note placeholders)"],
        "suggestions": ["string"],
        "preferred_steps": ["string (step-by-step implementation plan)"],
        "acceptance_criteria": ["string"],
        "test_scenarios": ["string"],
        "appendix": {"extracted_keywords": ["string"], "glossary": [{"term": "string", "definition": "string"}]}
    }

    user = (
        "Analyze the following BRD / process document and produce a 2+ page worth structured report.\n\n"
        "Return JSON only, matching this schema exactly (keys must exist, arrays can be empty):\n"
        f"{schema}\n\n"
        "Rules:\n"
        "- Prefer short bullets.\n"
        "- Include at least 18 functional requirements and 10 test scenarios when information allows.\n"
        "- If details are missing, infer carefully and add them to gaps_and_questions.\n"
        "- Add a diagrams_and_notes section describing suggested swimlane/flow diagram(s).\n\n"
        "DOCUMENT CONTENT:\n"
        f"""{document_text[:120000]}"""
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
        raise HTTPException(status_code=502, detail="Model returned non-JSON output")


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
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    mono = ParagraphStyle("Mono", parent=body, fontName="Courier", fontSize=9, leading=11)

    story = []

    story.append(_para(str(report.get("title") or "BRD Analysis Report"), h1))
    story.append(Spacer(1, 12))

    def section(title: str, content: Any):
        story.append(_para(title, h2))
        story.append(Spacer(1, 6))
        if content is None:
            story.append(_para("-", body))
        elif isinstance(content, str):
            story.append(_para(content, body))
        elif isinstance(content, list):
            if not content:
                story.append(_para("-", body))
            else:
                for item in content:
                    if isinstance(item, str):
                        story.append(_para(f"• {item}", body))
                    elif isinstance(item, dict):
                        story.append(_para(f"• {item}", mono))
                    else:
                        story.append(_para(f"• {str(item)}", body))
        elif isinstance(content, dict):
            for k, v in content.items():
                story.append(_para(f"{k}:", body))
                story.append(_para(str(v), mono))
        else:
            story.append(_para(str(content), body))
        story.append(Spacer(1, 10))

    section("Concise Summary", report.get("concise_summary"))
    section("Business Objectives", report.get("business_objectives"))
    section("Scope (In)", report.get("in_scope"))
    section("Scope (Out)", report.get("out_of_scope"))
    section("Stakeholders and Roles", report.get("stakeholders_and_roles"))

    story.append(PageBreak())

    section("Current Process", report.get("current_process"))
    section("Proposed Process", report.get("proposed_process"))
    section("Functional Requirements", report.get("functional_requirements"))
    section("Non-Functional Requirements", report.get("non_functional_requirements"))
    section("Data Entities", report.get("data_entities"))
    section("Integrations", report.get("integrations"))
    section("Assumptions", report.get("assumptions"))
    section("Dependencies", report.get("dependencies"))
    section("Risks", report.get("risks"))

    story.append(PageBreak())

    section("Gaps and Questions", report.get("gaps_and_questions"))
    section("Diagrams and Notes", report.get("diagrams_and_notes"))
    section("Suggestions", report.get("suggestions"))
    section("Preferred Steps", report.get("preferred_steps"))
    section("Acceptance Criteria", report.get("acceptance_criteria"))
    section("Test Scenarios", report.get("test_scenarios"))
    section("Appendix", report.get("appendix"))

    doc.build(story)
    return buf.getvalue()


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


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
