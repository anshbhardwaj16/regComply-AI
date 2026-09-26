from pydantic import BaseModel
from typing import Optional
from enum import Enum


class RiskLevel(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Obligation(BaseModel):
    id: str
    regulation_ref: str
    text: str
    category: str
    applicability: str


class Control(BaseModel):
    id: str
    policy_ref: str
    text: str
    category: str
    owner: str


class Mapping(BaseModel):
    obligation_id: str
    control_id: Optional[str]
    coverage: str  # "Full", "Partial", "None"
    confidence: float


class Gap(BaseModel):
    id: str
    obligation_id: str
    obligation_text: str
    regulation_ref: str
    coverage: str
    risk_level: RiskLevel
    risk_score: int
    reasoning: str


class Remediation(BaseModel):
    gap_id: str
    priority: int
    action: str
    owner: str
    timeline: str
    effort: str


class ComplianceReport(BaseModel):
    regulation_name: str
    total_obligations: int
    fully_covered: int
    partially_covered: int
    not_covered: int
    compliance_score: float
    obligations: list[Obligation]
    controls: list[Control]
    mappings: list[Mapping]
    gaps: list[Gap]
    remediations: list[Remediation]
    executive_summary: str


class AnalysisRequest(BaseModel):
    regulation_text: str
    control_text: str
    regulation_name: str = "Banking Regulation"
    bank_name: str = "Sample Bank"


class AnalysisStatus(BaseModel):
    stage: str
    message: str
    progress: int
