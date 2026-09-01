namespace Grant_finder
{
    public class Grant
    {
        public string? Title { get; set; }
        public string? Organization { get; set; }
        public string? Deadline { get; set; }
        public string? Category { get; set; } // The predicted category
        public string? FonteDeRecurso { get; set; }
        public string? PublicoAlvo { get; set; }
    }
}