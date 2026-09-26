import json
from backend.services.llm_client import llm_call, parse_json_response

PROMPT = """You are a banking regulatory compliance expert performing obligation-to-control mapping.

Map each regulatory obligation to the most relevant internal control.

Obligations:
{obligations}

Available Controls:
{controls}

For each obligation output:
- obligation_id: the obligation's id
- control_id: best matching control id, or null if none
- coverage: "Full" (control completely addresses obligation), "Partial" (partially addresses), or "None" (no match)
- confidence: float 0.0-1.0

Be strict: only "Full" if control clearly and completely addresses the obligation.
Gaps are valuable findings — do not force-fit poor matches.

Return a JSON array with one entry per obligation.
Return ONLY valid JSON — no markdown fences, no explanation."""


def map_obligations_to_controls(obligations: list[dict], controls: list[dict]) -> list[dict]:
    raw = llm_call(PROMPT.format(
        obligations=json.dumps(obligations, indent=2),
        controls=json.dumps(controls, indent=2)
    ), max_tokens=2500)
    return parse_json_response(raw)
