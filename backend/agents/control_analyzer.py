from backend.services.llm_client import llm_call, parse_json_response

EXTRACT_PROMPT = """You are a banking compliance expert analyzing internal control frameworks.

Analyze the following internal policy/control document and extract ALL distinct controls and policies.

For each control output:
- id: e.g. "CTL-001"
- policy_ref: document section reference if present
- text: clear description of what the control does (under 25 words)
- category: one of [Capital Adequacy, Liquidity, Risk Management, Governance, Reporting, KYC/AML, Consumer Protection, Cybersecurity, Operational]
- owner: responsible department/role (infer if not explicit)
- effectiveness_score: integer 0-100 estimating control effectiveness based on specificity, completeness, and automation level described in the text
- effectiveness_rating: "Strong" (>=75), "Adequate" (50-74), "Weak" (25-49), or "Insufficient" (<25)
- control_type: one of ["Preventive", "Detective", "Corrective", "Directive"]
- automation_level: one of ["Manual", "Semi-Automated", "Fully Automated"]

Control Document:
{text}

Return a JSON array. Extract exactly 5-8 controls. Be accurate with effectiveness scores.
Return ONLY valid JSON — no markdown fences, no explanation."""


def extract_controls(control_text: str) -> list[dict]:
    raw = llm_call(EXTRACT_PROMPT.format(text=control_text[:8000]), max_tokens=2500)
    return parse_json_response(raw)
