import { updateOpportunityDecision, OpportunityDecision } from "./utils/database.js";

const VALID_DECISIONS: OpportunityDecision[] = ["unreviewed", "apply", "watch", "dismiss", "favorite"];

function argValue(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  if (index < 0) {
    return undefined;
  }
  return process.argv[index + 1];
}

async function main(): Promise<void> {
  const keyOrUrl = argValue("--key") ?? argValue("--url");
  const decision = argValue("--decision") as OpportunityDecision | undefined;
  const notes = argValue("--notes");

  if (!keyOrUrl || !decision || !VALID_DECISIONS.includes(decision)) {
    console.error("Usage: npm run decide -- --key <opportunity-key-or-url> --decision <unreviewed|apply|watch|dismiss|favorite> [--notes <text>]");
    process.exitCode = 2;
    return;
  }

  const updated = await updateOpportunityDecision({ keyOrUrl, decision, notes });
  if (!updated) {
    console.error("No opportunity matched the provided key or URL.");
    process.exitCode = 1;
    return;
  }

  console.log(`Decision updated: ${decision}`);
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});

