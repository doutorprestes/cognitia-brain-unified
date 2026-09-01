using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Windows;

namespace Grant_finder
{
    public partial class MainWindow : Window
    {
        private readonly FinepScraperService _scraperService;

        public MainWindow()
        {
            InitializeComponent();
            _scraperService = new FinepScraperService();
        }

        private async void SearchButton_Click(object sender, RoutedEventArgs e)
        {
            StatusTextBlock.Text = "Buscando e classificando editais...";
            SearchButton.IsEnabled = false;

            bool findOnlyOpenGrants = OnlyOpenCheckBox.IsChecked ?? true;

            // This now correctly calls the method with the parameter
            List<Grant> scrapedGrants = await _scraperService.ScrapeAndClassifyGrants(findOnlyOpenGrants);

            ResultsDataGrid.ItemsSource = scrapedGrants;

            StatusTextBlock.Text = $"{scrapedGrants.Count} editais encontrados e classificados.";
            SearchButton.IsEnabled = true;
        }
    }
}