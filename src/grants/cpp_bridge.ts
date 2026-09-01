import { spawn } from "node:child_process";
import { RawOpportunity } from "../types.js";
import { createLogger } from "../utils/logger.js";

const logger = createLogger("cpp-bridge");

export async function fetchOpportunitiesWithCpp(source: "FAPESP" | "FINEP" | "ALL" = "ALL"): Promise<RawOpportunity[]> {
  return new Promise((resolve, reject) => {
    const process = spawn("./core-cpp/bin/grantwatch-core", [source]);
    let stdout = "";
    let stderr = "";

    process.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    process.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    process.on("close", (code) => {
      if (stderr) {
        logger.debug({ stderr }, "C++ Core stderr");
      }
      if (code !== 0) {
        reject(new Error(`C++ Core exited with code ${code}: ${stderr}`));
        return;
      }

      try {
        const results = JSON.parse(stdout) as RawOpportunity[];
        logger.info({ source, count: results.length }, "Fetched via C++ Core");
        resolve(results);
      } catch (err) {
        logger.error({ error: err, stdout }, "Failed to parse C++ Core output");
        resolve([]);
      }
    });
  });
}
