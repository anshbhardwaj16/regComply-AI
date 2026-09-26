import json
from backend.services.llm_client import llm_call, parse_json_response

CHANGE_PROMPT = """You are a regulatory change analyst specializing in banking compliance.

Compare these two versions of a banking regulation and identify ALL meaningful changes.

OLD REGULATION VERSION:
{old_text}

NEW REGULATION VERSION:
{new_text}

For each change output:
- id: e.g. "CHG-001"
- change_type: one of ["New Requirement", "Amended Requirement", "Removed Requirement", "Stricter Enforcement", "Relaxed Enforcement"]
- section_ref: section or clause reference (e.g. "Section 3.2")
- description: what changed in clear language (under 30 words)
- impact_level: "Critical", "High", "Medium", or "Low"
- affected_categories: array from [Capital Adequacy, Liquidity, Risk Management, Governance, Reporting, KYC/AML, Consumer Protection, Cybersecurity, Operational]
- compliance_action: what the bank must do to comply with this change (under 25 words)
- implementation_timeline: one of ["Immediate (0-30 days)", "Short-term (1-3 months)", "Medium-term (3-6 months)", "Long-term (6-12 months)"]

Return a JSON array sorted by impact_level (Critical first).
Return ONLY valid JSON — no markdown fences, no explanation."""

IMPACT_SUMMARY_PROMPT = """You are a Chief Risk Officer assessing regulatory change impact.

Regulation: {regulation_name}
Changes Detected: {total_changes}
Critical Changes: {critical}
High Impact Changes: {high}

Top Changes:
{top_changes}

Write a 3-4 sentence executive assessment of regulatory change impact and urgency for bank leadership.
Return only the assessment text, no JSON."""


def analyze_regulatory_changes(old_text: str, new_text: str, regulation_name: str = "Regulation") -> dict:
    raw = llm_call(CHANGE_PROMPT.format(
        old_text=old_text[:5000],
        new_text=new_text[:5000]
    ), max_tokens=3000)

    changes = parse_json_response(raw)

    critical = sum(1 for c in changes if c.get("impact_level") == "Critical")
    high = sum(1 for c in changes if c.get("impact_level") == "High")

    impact_summary = llm_call(IMPACT_SUMMARY_PROMPT.format(
        regulation_name=regulation_name,
        total_changes=len(changes),
        critical=critical,
        high=high,
        top_changes=json.dumps(changes[:3], indent=2)
    ), max_tokens=512)

    return {
        "changes": changes,
        "total_changes": len(changes),
        "critical_changes": critical,
        "high_impact_changes": high,
        "impact_summary": impact_summary,
    }
