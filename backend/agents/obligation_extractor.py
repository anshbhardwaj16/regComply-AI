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

Return a JSON array. Extract exactly 6-8 distinct obligations. Be concise — keep each "text" field under 25 words.
Return ONLY valid JSON — no markdown fences, no explanation."""


def extract_obligations(regulation_text: str) -> list[dict]:
    raw = llm_call(PROMPT.format(text=regulation_text[:8000]), max_tokens=2500)
    return parse_json_response(raw)
