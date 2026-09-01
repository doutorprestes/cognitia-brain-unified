import { z } from "zod";

import { Opportunity } from "../types.js";

export const RawOpportunitySchema = z.object({
  title: z.string().min(1),
  date: z.string(),
  link: z.string().url(),
  snippet: z.string(),
  source: z.string().optional(),
  opportunity_type: z.enum(["grant", "scholarship", "studentship", "fellowship", "other"]).optional(),
  raw_audience: z.string().optional(),
  funding_amount: z.string().optional()
});

export const ScoreBreakdownSchema = z.object({
  fit: z.number().min(0).max(100),
  eligibility: z.number().min(0).max(100),
  approval_probability: z.number().min(0).max(100),
  effort_vs_deadline: z.number().min(0).max(100),
  impact: z.number().min(0).max(100),
  total: z.number().min(0).max(100)
});

export const OpportunitySchema = RawOpportunitySchema.extend({
  source: z.string(),
  track: z.enum(["A", "B", "A/B"]),
  score: z.number().min(0).max(100),
  priority: z.enum(["aposta_principal", "aposta_tatica", "monitorar"]),
  score_breakdown: ScoreBreakdownSchema,
  eligibility_summary: z.string().optional(),
  eligibility_confidence: z.number().min(0).max(100).optional()
});

export const ProfileRequirementsSchema = z.object({
  profile_id: z.string(),
  source_pdf: z.string(),
  last_updated: z.string(),
  objective: z.string(),
  hard_filters: z.object({
    include_any_technical_core: z.array(z.string()),
    include_any_application_context: z.array(z.string()),
    required_audience_any: z.array(z.string()),
    exclude_any: z.array(z.string()),
    soft_exclude_any: z.array(z.string()).optional(),
    deadline_min_days: z.number().min(0)
  }),
  scoring: z.object({
    weights: z.object({
      thematic_fit: z.number().min(0).max(100),
      eligibility_fit: z.number().min(0).max(100),
      methodological_fit: z.number().min(0).max(100),
      timeline_fit: z.number().min(0).max(100),
      resource_fit: z.number().min(0).max(100)
    }),
    thresholds: z.object({
      go: z.number().min(0).max(100),
      watch: z.number().min(0).max(100)
    }),
    thematic_fit_terms: z.object({
      high: z.array(z.string()),
      medium: z.array(z.string()),
      low: z.array(z.string())
    }),
    methodological_fit_terms: z.array(z.string()),
    resource_fit_terms: z.array(z.string())
  }),
  required_output_fields: z.array(z.string())
});

export type RawOpportunityInput = z.input<typeof RawOpportunitySchema>;
export type OpportunityInput = z.input<typeof OpportunitySchema>;
export type ProfileRequirementsInput = z.input<typeof ProfileRequirementsSchema>;

export function validateRawOpportunity(data: unknown) {
  return RawOpportunitySchema.safeParse(data);
}

export function validateOpportunity(data: unknown) {
  return OpportunitySchema.safeParse(data);
}

export function validateProfileRequirements(data: unknown) {
  return ProfileRequirementsSchema.safeParse(data);
}

export function validateOpportunities(data: unknown): { valid: Opportunity[]; invalid: unknown[] } {
  if (!Array.isArray(data)) {
    return { valid: [], invalid: [data] };
  }
  
  const valid: Opportunity[] = [];
  const invalid: unknown[] = [];
  
  for (const item of data) {
    const result = OpportunitySchema.safeParse(item);
    if (result.success) {
      valid.push(result.data);
    } else {
      invalid.push(item);
    }
  }
  
  return { valid, invalid };
}
