import axios from "axios";
import { RawOpportunity } from "../types.js";
import { fetchWithRetry, parseGenericOpportunities } from "./common.js";

const EMBRAPII_URL = "https://embrapii.org.br/transparencia/";

export async function fetchEmbrapiiOpportunities(): Promise<RawOpportunity[]> {
  const response = await fetchWithRetry(async () => {
    return axios.get<string>(EMBRAPII_URL, {
      timeout: 30000,
      headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" 
      }
    });
  });

  return parseGenericOpportunities(response.data, EMBRAPII_URL, {
    selectors: ".single-chamada-publica",
    minTitleLength: 10,
    keywords: /chamada|edital|projeto|inovação|p&d|competência|saúde|empresa/i,
    source: "EMBRAPII"
  });
}
