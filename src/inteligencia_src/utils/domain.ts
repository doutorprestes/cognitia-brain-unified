import { RawOpportunity } from "../types.js";

function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

const IN_DOMAIN_TERMS = [
  "robot",
  "robotics",
  "humanoid",
  "autonomous",
  "artificial intelligence",
  "machine learning",
  "deep learning",
  "reinforcement learning",
  "multi-agent",
  "marl",
  "intelligent systems",
  "control systems",
  "large language model",
  "llm",
  "llms",
  "theory of mind",
  "human-ai interaction",
  "artificial agency"
];

const OUT_OF_DOMAIN_TERMS = [
  "cardiovascular",
  "microbial",
  "neuroscience",
  "clinical",
  "hiv",
  "rehabilitation",
  "public safety",
  "law enforcement",
  "offender",
  "crime",
  "humanities",
  "agriculture"
];

export function domainRelevance(item: RawOpportunity): { in_domain: boolean; score: number; reason: string } {
  const text = normalize(`${item.title} ${item.snippet}`);
  const inHits = IN_DOMAIN_TERMS.filter((t) => text.includes(normalize(t))).length;
  const outHits = OUT_OF_DOMAIN_TERMS.filter((t) => text.includes(normalize(t))).length;

  const score = Math.max(0, Math.min(100, inHits * 25 - outHits * 20 + (inHits > 0 ? 30 : 0)));
  const inDomain = score >= 35;
  const reason = `in_hits=${inHits}; out_hits=${outHits}; domain_score=${score}`;

  return { in_domain: inDomain, score, reason };
}
