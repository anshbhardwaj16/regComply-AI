import json
from backend.services.llm_client import llm_call, parse_json_response

PROMPT = """You are a banking compliance transformation expert recommending remediation actions.

For each compliance gap, provide a concrete remediation plan.

Gaps (sorted by risk, highest first):
{gaps}

For each gap output:
- gap_id: the gap's id
- priority: integer 1-N (1 = highest priority)
- action: specific, concrete action the bank must take (2-3 sentences)
- owner: department/role responsible (e.g., "Risk Management", "Compliance Officer", "IT Security")
- timeline: realistic timeline (e.g., "Immediate (0-30 days)", "Short-term (1-3 months)", "Medium-term (3-6 months)")
- effort: "Low", "Medium", "High", or "Very High"

Keep each "action" under 30 words. Be specific and actionable.

Return a JSON array.
Return ONLY valid JSON — no markdown fences, no explanation."""


SUMMARY_PROMPT = """You are a Chief Compliance Officer writing an executive summary.

Compliance Analysis Results:
- Total Obligations: {total}
- Fully Covered: {full}
- Partially Covered: {partial}
- Not Covered: {none}
- Compliance Score: {score:.1f}%
- Critical Gaps: {critical}
- High Risk Gaps: {high}

Top Gaps:
{top_gaps}

Write a 3-4 sentence executive summary for the bank's board. Be direct about risks and urgency.
Return only the summary text, no JSON."""


def generate_remediations(gaps: list[dict]) -> list[dict]:
    if not gaps:
        return []
    raw = llm_call(PROMPT.format(gaps=json.dumps(gaps, indent=2)), max_tokens=2000)
    return parse_json_response(raw)


def generate_executive_summary(
    total: int, full: int, partial: int, none_count: int, score: float, gaps: list[dict]
) -> str:
    critical = sum(1 for g in gaps if g.get("risk_level") == "Critical")
    high = sum(1 for g in gaps if g.get("risk_level") == "High")
    top_gaps = json.dumps(gaps[:3], indent=2) if gaps else "None"

    return llm_call(SUMMARY_PROMPT.format(
        total=total, full=full, partial=partial, none=none_count,
        score=score, critical=critical, high=high, top_gaps=top_gaps
    ), max_tokens=512)
