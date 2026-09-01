import axios from "axios";
import { RawOpportunity } from "../types.js";
import { fetchWithRetry, parseGenericOpportunities } from "./common.js";

const INOVA_URL = "https://www.inova.unicamp.br/category/parceria-pesquisa-mercado/editais-e-chamadas-de-financiamento/";

export async function fetchInovaOpportunities(): Promise<RawOpportunity[]> {
  const response = await fetchWithRetry(async () => {
    return axios.get<string>(INOVA_URL, {
      timeout: 30000,
      headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" 
      }
    });
  });

  return parseGenericOpportunities(response.data, INOVA_URL, {
    selectors: "article",
    minTitleLength: 10,
    keywords: /edital|chamada|oportunidade|financiamento|parceria|inovação|tecnologia/i,
    source: "Inova Unicamp"
  });
}
