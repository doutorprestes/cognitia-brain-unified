import axios from "axios";
import { RawOpportunity } from "../types.js";
import { fetchWithRetry, parseGenericOpportunities } from "./common.js";

const CIMATEC_URL = "https://www.universidadesenaicimatec.edu.br/editais-e-documentos/";

export async function fetchCimatecOpportunities(): Promise<RawOpportunity[]> {
  const response = await fetchWithRetry(async () => {
    return axios.get<string>(CIMATEC_URL, {
      timeout: 30000,
      headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" 
      }
    });
  });

  return parseGenericOpportunities(response.data, CIMATEC_URL, {
    selectors: ".accordion-body p",
    minTitleLength: 15,
    keywords: /edital|chamada|bolsa|fomento|estudant|projeto|seleção/i,
    source: "SENAI CIMATEC"
  });
}
