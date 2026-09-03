#!/usr/bin/env python3
"""Script principal de coleta - executa todos os scrapers."""
import sys
import os
from datetime import datetime

# Adiciona o path do projeto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scrapers.grants.scraper_editais import ScraperEditais
from src.scrapers.artigos.scraper_artigos import ScraperArtigos

def main():
    print(f"🌐 CognitiaBrain - Coleta de Dados")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # Artigos
    print("\n📝 COLETANDO ARTIGOS...")
    artigos = ScraperArtigos()
    total_artigos = artigos.coletar_tudo()
    
    # Editais/Grants
    print("\n📜 COLETANDO EDITAIS...")
    editais = ScraperEditais()
    total_editais = editais.coletar_tudo()
    
    print("\n" + "=" * 50)
    print(f"✅ Coleta concluída!")
    print(f"   📝 Artigos: {total_artigos}")
    print(f"   📜 Editais: {total_editais}")
    print(f"   📊 Total: {total_artigos + total_editais}")

if __name__ == "__main__":
    main()
