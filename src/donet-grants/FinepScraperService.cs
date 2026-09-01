using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net.Http;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;

namespace Grant_finder
{
    public class FinepScraperService
    {
        private static readonly HttpClient client = new HttpClient();

        public FinepScraperService()
        {
            client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36");
        }

        public async Task<List<Grant>> ScrapeAndClassifyGrants(bool onlyOpen)
        {
            var grantList = new List<Grant>();
            try
            {
                var baseUrl = "http://www.finep.gov.br/chamadas-publicas";

                for (int i = 0; i < 20; i++)
                {
                    var pageNumber = i * 10;
                    var url = (i == 0) ? baseUrl : $"{baseUrl}?start={pageNumber}";
                    string htmlContent = await client.GetStringAsync(url);

                    var blockPattern = @"<div class=""item"">(.*?)<div class=""item"">";
                    var matches = Regex.Matches(htmlContent + @"<div class=""item"">", blockPattern, RegexOptions.Singleline);

                    if (matches.Count == 0 && i > 0) break;

                    foreach (Match match in matches)
                    {
                        string cardHtml = match.Groups[1].Value;

                        var titleMatch = Regex.Match(cardHtml, @"<h3><a.*?>(.*?)</a></h3>", RegexOptions.Singleline);
                        var deadlineMatch = Regex.Match(cardHtml, @"<div class=""prazo div"">.*?<span>(.*?)</span></div>", RegexOptions.Singleline);

                        if (titleMatch.Success)
                        {
                            string title = titleMatch.Groups[1].Value.Trim();
                            string deadlineString = deadlineMatch.Success ? deadlineMatch.Groups[1].Value.Trim() : "N/A";

                            bool isGrantOpen = false;
                            if (deadlineString != "N/A" && DateTime.TryParseExact(deadlineString, "dd/MM/yyyy", CultureInfo.GetCultureInfo("pt-BR"), DateTimeStyles.None, out DateTime deadlineDate))
                            {
                                if (deadlineDate.Date >= DateTime.Today)
                                {
                                    isGrantOpen = true;
                                }
                            }

                            if (onlyOpen == false || isGrantOpen == true)
                            {
                                // If the grant matches our filter, we proceed to classify and add it.
                                var fonteMatch = Regex.Match(cardHtml, @"<div class=""fonte div"">.*?<span>(.*?)</span>", RegexOptions.Singleline);
                                var alvoMatch = Regex.Match(cardHtml, @"<div class=""publico div"">.*?<span class=""tag"">(.*?)</span>", RegexOptions.Singleline);

                                var grant = new Grant
                                {
                                    Title = title,
                                    FonteDeRecurso = fonteMatch.Success ? fonteMatch.Groups[1].Value.Trim() : "",
                                    PublicoAlvo = alvoMatch.Success ? alvoMatch.Groups[1].Value.Trim() : "",
                                    Deadline = deadlineString,
                                    Organization = "FINEP"
                                };

                                var modelInput = new GrantClassifier.ModelInput()
                                {
                                    Title = grant.Title ?? "",
                                    FonteDeRecurso = grant.FonteDeRecurso ?? "",
                                    PublicoAlvo = grant.PublicoAlvo ?? ""
                                };

                                var prediction = GrantClassifier.Predict(modelInput);
                                grant.Category = prediction.PredictedLabel;

                                grantList.Add(grant);
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Ocorreu um erro ao buscar os dados: {ex.Message}");
            }
            return grantList;
        }
    }
}