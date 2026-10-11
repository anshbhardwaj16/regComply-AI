from backend.services.llm_client import llm_call, parse_json_response

PROMPT = """You are a regulatory compliance expert specializing in banking regulations.

Analyze the following regulatory text and extract ALL specific obligations a bank must comply with.

For each obligation output:
- id: e.g. "OBL-001"
- regulation_ref: section/clause reference if present
- text: the obligation in clear, actionable language
- category: one of [Capital Adequacy, Liquidity, Risk Management, Governance, Reporting, KYC/AML, Consumer Protection, Cybersecurity, Operational]
- applicability: who this applies to

Regulatory Text:
{text}

Return a JSON array. Extract every distinct obligation, typically one per numbered clause (up to 20).
Keep each "text" field under 30 words, and keep every specific parameter exactly as stated: frequencies, deadlines, thresholds, amounts, retention periods and scope.
Return ONLY valid JSON — no markdown fences, no explanation."""


def extract_obligations(regulation_text: str) -> list[dict]:
    raw = llm_call(PROMPT.format(text=regulation_text[:8000]), max_tokens=4000)
    return parse_json_response(raw)
