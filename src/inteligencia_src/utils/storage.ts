import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { Opportunity } from "../types.js";
import { validateOpportunities } from "./validation.js";
import { createLogger } from "./logger.js";
import { loadPreviousFromDatabase } from "./database.js";

const logger = createLogger("storage");
const DATA_DIR = process.env.DATA_DIR || ".";
export const DATA_FILE = join(DATA_DIR, "data", "last_fetch.json");

export async function loadPrevious(): Promise<Opportunity[]> {
  const fromDatabase = await loadPreviousFromDatabase();
  if (fromDatabase.length > 0) {
    return fromDatabase;
  }

  try {
    const content = await readFile(DATA_FILE, "utf8");
    const sanitized = content.replace(/^\uFEFF/, "");
    const parsed = JSON.parse(sanitized);
    
    if (!Array.isArray(parsed)) {
      logger.warn("Invalid data format: expected array");
      return [];
    }
    
    const { valid, invalid } = validateOpportunities(parsed);
    
    if (invalid.length > 0) {
      logger.warn({ invalidCount: invalid.length }, "Some items failed validation");
    }
    
    logger.info({ count: valid.length }, "Loaded previous items");
    return valid;
  } catch (error) {
    logger.debug({ error }, "No previous data found");
    return [];
  }
}

export async function saveCurrent(items: Opportunity[]): Promise<void> {
  await mkdir(join(DATA_DIR, "data"), { recursive: true });
  await writeFile(DATA_FILE, `${JSON.stringify(items, null, 2)}\n`, "utf8");
  logger.info({ count: items.length }, "Saved current items");
}
