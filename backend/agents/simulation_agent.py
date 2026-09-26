import json
from backend.services.llm_client import llm_call, parse_json_response

SIMULATION_PROMPT = """You are a senior banking regulatory simulation expert performing what-if compliance analysis.

CURRENT COMPLIANCE STATE:
Bank: {bank_name}
Regulation: {regulation_name}
Current Compliance Score: {score}%
Fully Covered Obligations: {full}
Partially Covered: {partial}
Not Covered: {not_covered}

Current Gaps (top 5):
{gaps}

Current Controls (top 5):
{controls}

HYPOTHETICAL SCENARIO TO SIMULATE:
{scenario}

Simulate the impact of this scenario on the bank's compliance posture. Return a JSON object with:
- scenario_summary: brief restatement of the scenario (under 20 words)
- new_compliance_score: estimated new compliance score 0-100 as integer
- score_delta: change from current score (positive or negative integer)
- newly_created_gaps: array of new gaps this scenario would create, each with:
  - id: "SIM-GAP-001" etc.
  - description: what obligation would now be violated (under 25 words)
  - risk_level: "Critical", "High", "Medium", or "Low"
  - affected_control: which existing control would be impacted
- closed_gaps: array of gap ids that would be resolved by this scenario (use ids from current gaps)
- affected_obligations: list of obligation IDs impacted (e.g. ["OBL-001", "OBL-003"])
- required_actions: array of actions the bank must take, each with:
  - action: what to do (under 25 words)
  - priority: "Immediate", "Short-term", or "Medium-term"
  - effort: "Low", "Medium", or "High"
- simulation_narrative: 3-4 sentence narrative of what would happen for board reporting

Return ONLY valid JSON — no markdown fences, no explanation."""


def simulate_scenario(
    scenario: str,
    bank_name: str,
    regulation_name: str,
    score: float,
    full: int,
    partial: int,
    not_covered: int,
    gaps: list,
    controls: list,
) -> dict:
    raw = llm_call(
        SIMULATION_PROMPT.format(
            bank_name=bank_name,
            regulation_name=regulation_name,
            score=round(score, 1),
            full=full,
            partial=partial,
            not_covered=not_covered,
            gaps=json.dumps(gaps[:5], indent=2),
            controls=json.dumps(controls[:5], indent=2),
            scenario=scenario,
        ),
        max_tokens=3000,
    )
    return parse_json_response(raw)
