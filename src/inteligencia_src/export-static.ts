import { loadPrevious } from "./utils/storage.js";
import { writeStaticApiPayload } from "./utils/uiPayload.js";
import { createLogger } from "./utils/logger.js";

const logger = createLogger("export-static");

async function main(): Promise<void> {
  const items = await loadPrevious();
  await writeStaticApiPayload(items);
  logger.info({ count: items.length }, "Static API payload exported");
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? err.stack ?? err.message : String(err);
  logger.error({ error: message }, "Static export failed");
  process.exitCode = 1;
});

