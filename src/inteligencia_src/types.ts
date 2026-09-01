export type Track = "A" | "B" | "A/B";
export type Priority = "aposta_principal" | "aposta_tatica" | "monitorar";

export type RawOpportunity = {
  title: string;
  date: string;
  link: string;
  snippet: string;
  source?: string;
  opportunity_type?: "grant" | "scholarship" | "studentship" | "fellowship" | "other";
  raw_audience?: string;
  funding_amount?: string;
};

export type ScoreBreakdown = {
  fit: number;
  eligibility: number;
  approval_probability: number;
  effort_vs_deadline: number;
  impact: number;
  total: number;
};

export type Opportunity = RawOpportunity & {
  source: string;
  track: Track;
  score: number;
  priority: Priority;
  score_breakdown: ScoreBreakdown;
  eligibility_summary?: string;
  eligibility_confidence?: number;
  ai_analysis?: {
    executive_summary: string;
    adherence_score: number;
    justification: string;
    eligibility_criteria: string[];
    themes: string[];
    keywords: string[];
    type: "bolsa-pessoal" | "grant-projeto";
    funding_amount: string;
  };
};

export type EligibilityAssessment = {
  audience_matches: string[];
  degree_level_matches: string[];
  institution_matches: string[];
  visa_or_nationality_notes: string[];
  confidence: number;
  summary: string;
};

export type ProfileRequirements = {
  profile_id: string;
  source_pdf: string;
  last_updated: string;
  objective: string;
  hard_filters: {
    include_any_technical_core: string[];
    include_any_application_context: string[];
    required_audience_any: string[];
    exclude_any: string[];
    soft_exclude_any?: string[];
    deadline_min_days: number;
  };
  scoring: {
    weights: {
      thematic_fit: number;
      eligibility_fit: number;
      methodological_fit: number;
      timeline_fit: number;
      resource_fit: number;
    };
    thresholds: {
      go: number;
      watch: number;
    };
    thematic_fit_terms: {
      high: string[];
      medium: string[];
      low: string[];
    };
    methodological_fit_terms: string[];
    resource_fit_terms: string[];
  };
  required_output_fields: string[];
};

/** Scrapers internos retornam este formato; mapeado para RawOpportunity no retorno */
export type ScrapedItem = {
  id: string;
  source: string;
  title: string;
  summary: string;
  url: string;
  pdfUrl?: string;
  authors?: string;
  publishedDate: string;
  category?: string;
  venue?: string;
  citationCount?: number;
  type: string;
  rawData?: unknown;
};

export type ScraperConfig = {
  keywords?: string[];
  topics?: string[];
  categories?: string[];
  maxResults?: number;
  daysBack?: number;
  limit?: number;
  source?: string;
};
