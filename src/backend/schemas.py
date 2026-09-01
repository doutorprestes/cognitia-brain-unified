from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ThemeSchema(BaseModel):
    id: str
    label: str
    description: str
    tone: str
    implication: str
    decision_question: str

class SourceMetadata(BaseModel):
    source_id: str
    source_name: str
    official_url: str
    collection_method: str
    update_frequency: str
    processed_file: str
    is_demo: bool
    status: str
    data_status: str
    collected_at: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    schema_version: Optional[str] = None
    raw_format: Optional[str] = None
    processed_format: Optional[str] = None
    record_count: Optional[int] = None
    last_error: Optional[str] = None
    known_limitations: Optional[str] = None

class PublicAgendaSignal(BaseModel):
    signal_id: str
    source_id: str
    source_name: str
    signal_type: str
    title: str
    summary: str
    date: str
    theme: ThemeSchema
    policy_axis: str
    decision_relevance: str
    official_url: str
    is_demo: bool
    data_status: str
    collected_at: Optional[str] = None
    known_limitations: Optional[str] = None
    # Extra fields for legislative signals
    siglaTipo: Optional[str] = None
    numero: Optional[str] = None
    ano: Optional[str] = None
    primary_author: Optional[str] = None
    status_legislativo: Optional[str] = None
    urgency_level: Optional[str] = None
    latest_tramitacao_descricao: Optional[str] = None
    display_label: Optional[str] = None

class SignalTypeSummary(BaseModel):
    signal_type: str
    label: str
    count: int
    sources: List[str]

class SourceContribution(BaseModel):
    source_id: str
    source_name: str
    signal_count: int
    last_collected_at: Optional[str]
    status: str
    is_demo: bool

class ExecutiveBriefing(BaseModel):
    updated_at: str
    coverage: Dict[str, Any] # e.g. {"signals_analyzed": 10, ...}
    signals_by_type: List[SignalTypeSummary]
    source_contributions: List[SourceContribution]
    latest_signals: List[PublicAgendaSignal]

class SourceStatusSummary(BaseModel):
    registered: int
    real: int
    demo: int
    missing: int
    stale: int
    failed: int
    real_source_names: List[str]
    demo_source_names: List[str]
    missing_source_names: List[str]
    stale_source_names: List[str]
    failed_source_names: List[str]

class CamaraStats(BaseModel):
    total_propositions: int
    by_type: Dict[str, int]
    is_demo: bool
    source: str
    last_collected_at: Optional[str] = None

class FundingSignal(BaseModel):
    label: str
    value: str
    reference: str
    source: str
    is_demo: bool

class FundingBriefing(BaseModel):
    title: str
    question: str
    generated_at: str
    is_demo: bool
    signals: List[FundingSignal]
    items: Dict[str, Any]
    decision_questions: List[str]
    source_status: List[SourceMetadata]
    known_gaps: List[str]

class MethodologyStep(BaseModel):
    step: str
    description: str

class ExecutiveSourceCandidate(BaseModel):
    source_id: str
    source_name: str
    status: str
    priority: str
    rationale: str

class MethodologyReport(BaseModel):
    title: str
    generated_at: str
    data_quality: Dict[str, Any]
    lifecycle: List[MethodologyStep]
    classification: str
    executive_source_candidates: List[ExecutiveSourceCandidate]
    limitations: List[str]
    sources: List[SourceMetadata]

class PropositionsResponse(BaseModel):
    items: List[PublicAgendaSignal]
    count: int
    total_available: int
    is_demo: bool
    source: str
    last_collected_at: Optional[str]
    filters: Optional[Dict[str, Any]] = None

class PublicationsResponse(BaseModel):
    items: List[Dict[str, Any]] # Still generic as DOU rows vary
    count: int
    is_demo: bool
    source: str
    last_collected_at: Optional[str] = None

class SearchResult(BaseModel):
    items: List[PublicAgendaSignal]
    total: int
    page: int
    limit: int

class HealthResponse(BaseModel):
    status: str
    service_status: str
    checked_at: str
    data_dir: str
    sources: Dict[str, bool]
    source_statuses: Dict[str, str]
    demo_sources: List[str]
    missing_sources: List[str]
    stale_sources: List[str]
    failed_sources: List[str]
    degraded_sources: List[str]
