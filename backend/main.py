import os
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import uvicorn

from backend.services.document_processor import process_document
from backend.agents.obligation_extractor import extract_obligations
from backend.agents.control_analyzer import extract_controls
from backend.agents.mapper import map_obligations_to_controls
from backend.agents.gap_analyzer import analyze_gaps
from backend.agents.remediation_agent import generate_remediations, generate_executive_summary
from backend.agents.regulatory_change_agent import analyze_regulatory_changes
from backend.agents.simulation_agent import simulate_scenario

app = FastAPI(title="RegComply AI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
async def root():
    index = os.path.join(frontend_path, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "RegComply AI API running"}


@app.get("/health")
async def health():
    provider = os.getenv("LLM_PROVIDER", "groq")
    return {"status": "healthy", "provider": provider, "version": "2.0.0"}


def _build_result(regulation_name, bank_name, obligations, controls, mappings, gaps, remediations, summary):
    total = len(obligations)
    full = sum(1 for m in mappings if m.get("coverage") == "Full")
    partial = sum(1 for m in mappings if m.get("coverage") == "Partial")
    none_count = sum(1 for m in mappings if m.get("coverage") == "None")
    score = (full + partial * 0.5) / total * 100 if total > 0 else 0
    return {
        "regulation_name": regulation_name,
        "bank_name": bank_name,
        "total_obligations": total,
        "fully_covered": full,
        "partially_covered": partial,
        "not_covered": none_count,
        "compliance_score": round(score, 1),
        "obligations": obligations,
        "controls": controls,
        "mappings": mappings,
        "gaps": gaps,
        "remediations": remediations,
        "executive_summary": summary,
    }


# ── Streaming SSE endpoint ────────────────────────────────────────────────────

@app.post("/api/analyze-stream")
async def analyze_stream(
    regulation_file: UploadFile = File(None),
    control_file: UploadFile = File(None),
    regulation_text: str = Form(None),
    control_text: str = Form(None),
    regulation_name: str = Form("Banking Regulation"),
    bank_name: str = Form("Sample Bank"),
):
    if regulation_file:
        reg_bytes = await regulation_file.read()
        reg_text = process_document(regulation_file.filename, reg_bytes)
    elif regulation_text:
        reg_text = regulation_text
    else:
        raise HTTPException(400, "Provide regulation_file or regulation_text")

    if control_file:
        ctl_bytes = await control_file.read()
        ctl_text = process_document(control_file.filename, ctl_bytes)
    elif control_text:
        ctl_text = control_text
    else:
        raise HTTPException(400, "Provide control_file or control_text")

    async def event_stream():
        loop = asyncio.get_event_loop()

        def emit(event: str, data: dict) -> str:
            return f"data: {json.dumps({'event': event, **data})}\n\n"

        try:
            yield emit("step", {"step": "ingestion", "status": "done", "msg": "Documents ingested"})

            obligations = await loop.run_in_executor(None, extract_obligations, reg_text)
            yield emit("step", {"step": "obligations", "status": "done",
                                "msg": f"Extracted {len(obligations)} obligations", "count": len(obligations)})

            controls = await loop.run_in_executor(None, extract_controls, ctl_text)
            yield emit("step", {"step": "controls", "status": "done",
                                "msg": f"Analyzed {len(controls)} controls", "count": len(controls)})

            mappings = await loop.run_in_executor(None, map_obligations_to_controls, obligations, controls)
            yield emit("step", {"step": "mapping", "status": "done", "msg": "Obligation-to-control mapping complete"})

            gaps = await loop.run_in_executor(None, analyze_gaps, obligations, mappings)
            yield emit("step", {"step": "gaps", "status": "done",
                                "msg": f"Identified {len(gaps)} compliance gaps", "count": len(gaps)})

            remediations = await loop.run_in_executor(None, generate_remediations, gaps)
            yield emit("step", {"step": "remediation", "status": "done",
                                "msg": f"Generated {len(remediations)} remediation actions"})

            total = len(obligations)
            full = sum(1 for m in mappings if m.get("coverage") == "Full")
            partial_c = sum(1 for m in mappings if m.get("coverage") == "Partial")
            none_count = sum(1 for m in mappings if m.get("coverage") == "None")
            score = (full + partial_c * 0.5) / total * 100 if total > 0 else 0

            summary = await loop.run_in_executor(
                None, generate_executive_summary, total, full, partial_c, none_count, score, gaps
            )

            result = {
                "regulation_name": regulation_name,
                "bank_name": bank_name,
                "total_obligations": total,
                "fully_covered": full,
                "partially_covered": partial_c,
                "not_covered": none_count,
                "compliance_score": round(score, 1),
                "obligations": obligations,
                "controls": controls,
                "mappings": mappings,
                "gaps": gaps,
                "remediations": remediations,
                "executive_summary": summary,
            }
            yield emit("complete", {"result": result})

        except Exception as exc:
            yield emit("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Standard (non-streaming) analyze endpoints ────────────────────────────────

@app.post("/api/analyze")
async def analyze(
    regulation_file: UploadFile = File(None),
    control_file: UploadFile = File(None),
    regulation_text: str = Form(None),
    control_text: str = Form(None),
    regulation_name: str = Form("Banking Regulation"),
    bank_name: str = Form("Sample Bank"),
):
    if regulation_file:
        reg_bytes = await regulation_file.read()
        reg_text = process_document(regulation_file.filename, reg_bytes)
    elif regulation_text:
        reg_text = regulation_text
    else:
        raise HTTPException(400, "Provide regulation_file or regulation_text")

    if control_file:
        ctl_bytes = await control_file.read()
        ctl_text = process_document(control_file.filename, ctl_bytes)
    elif control_text:
        ctl_text = control_text
    else:
        raise HTTPException(400, "Provide control_file or control_text")

    loop = asyncio.get_event_loop()
    obligations = await loop.run_in_executor(None, extract_obligations, reg_text)
    controls = await loop.run_in_executor(None, extract_controls, ctl_text)
    mappings = await loop.run_in_executor(None, map_obligations_to_controls, obligations, controls)
    gaps = await loop.run_in_executor(None, analyze_gaps, obligations, mappings)
    remediations = await loop.run_in_executor(None, generate_remediations, gaps)

    total = len(obligations)
    full = sum(1 for m in mappings if m.get("coverage") == "Full")
    partial = sum(1 for m in mappings if m.get("coverage") == "Partial")
    none_count = sum(1 for m in mappings if m.get("coverage") == "None")
    score = (full + partial * 0.5) / total * 100 if total > 0 else 0

    summary = await loop.run_in_executor(
        None, generate_executive_summary, total, full, partial, none_count, score, gaps
    )

    return _build_result(regulation_name, bank_name, obligations, controls, mappings, gaps, remediations, summary)


@app.post("/api/analyze-text")
async def analyze_text(body: dict):
    reg_text = body.get("regulation_text", "")
    ctl_text = body.get("control_text", "")
    regulation_name = body.get("regulation_name", "Banking Regulation")
    bank_name = body.get("bank_name", "Sample Bank")

    if not reg_text or not ctl_text:
        raise HTTPException(400, "regulation_text and control_text are required")

    loop = asyncio.get_event_loop()
    obligations = await loop.run_in_executor(None, extract_obligations, reg_text)
    controls = await loop.run_in_executor(None, extract_controls, ctl_text)
    mappings = await loop.run_in_executor(None, map_obligations_to_controls, obligations, controls)
    gaps = await loop.run_in_executor(None, analyze_gaps, obligations, mappings)
    remediations = await loop.run_in_executor(None, generate_remediations, gaps)

    total = len(obligations)
    full = sum(1 for m in mappings if m.get("coverage") == "Full")
    partial = sum(1 for m in mappings if m.get("coverage") == "Partial")
    none_count = sum(1 for m in mappings if m.get("coverage") == "None")
    score = (full + partial * 0.5) / total * 100 if total > 0 else 0

    summary = await loop.run_in_executor(
        None, generate_executive_summary, total, full, partial, none_count, score, gaps
    )

    return _build_result(regulation_name, bank_name, obligations, controls, mappings, gaps, remediations, summary)


# ── Regulatory Change Intelligence ───────────────────────────────────────────

@app.post("/api/change-analysis")
async def change_analysis(body: dict):
    old_text = body.get("old_regulation_text", "")
    new_text = body.get("new_regulation_text", "")
    regulation_name = body.get("regulation_name", "Regulation")

    if not old_text or not new_text:
        raise HTTPException(400, "old_regulation_text and new_regulation_text are required")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, analyze_regulatory_changes, old_text, new_text, regulation_name
    )
    return result


# ── What-if Simulation ────────────────────────────────────────────────────────

@app.post("/api/simulate")
async def simulate(body: dict):
    scenario = body.get("scenario", "")
    if not scenario:
        raise HTTPException(400, "scenario is required")

    bank_name = body.get("bank_name", "Sample Bank")
    regulation_name = body.get("regulation_name", "Banking Regulation")
    score = body.get("compliance_score", 0)
    full = body.get("fully_covered", 0)
    partial = body.get("partially_covered", 0)
    not_covered = body.get("not_covered", 0)
    gaps = body.get("gaps", [])
    controls = body.get("controls", [])

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        simulate_scenario,
        scenario, bank_name, regulation_name,
        score, full, partial, not_covered, gaps, controls,
    )
    return result


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
