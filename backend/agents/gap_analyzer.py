import json
from backend.services.llm_client import llm_call, parse_json_response

PROMPT = """You are a senior banking regulatory risk expert identifying compliance gaps.

Based on the obligations and their control coverage, identify all compliance gaps.

Obligations with coverage:
{obligations_with_coverage}

For each gap (obligations with "Partial" or "None" coverage), output:
- id: e.g. "GAP-001"
- obligation_id: the obligation id
- obligation_text: the obligation text
- regulation_ref: the regulation reference
- coverage: "Partial" or "None"
- risk_level: "Critical", "High", "Medium", or "Low"
- risk_score: integer 1-100 (100 = most critical)
- reasoning: why this is a risk and what could go wrong

Risk scoring guidance:
- Critical (80-100): Regulatory penalty, license risk, systemic failure
- High (60-79): Significant operational/financial exposure
- Medium (40-59): Moderate risk, manageable but needs attention
- Low (1-39): Minor gap, limited immediate impact

Keep "reasoning" under 20 words per gap.
Return a JSON array sorted by risk_score descending.
Return ONLY valid JSON — no markdown fences, no explanation."""


def analyze_gaps(obligations: list[dict], mappings: list[dict]) -> list[dict]:
    # Enrich obligations with coverage info
    coverage_map = {m["obligation_id"]: m for m in mappings}
    obligations_with_coverage = []
    for obl in obligations:
        mapping = coverage_map.get(obl["id"], {})
        obligations_with_coverage.append({
            **obl,
            "coverage": mapping.get("coverage", "None"),
            "control_id": mapping.get("control_id"),
        })

    # Only analyze non-Full obligations
    gaps_to_analyze = [o for o in obligations_with_coverage if o["coverage"] != "Full"]
    if not gaps_to_analyze:
        return []

    raw = llm_call(PROMPT.format(
        obligations_with_coverage=json.dumps(gaps_to_analyze, indent=2)
    ), max_tokens=2000)
    return parse_json_response(raw)
