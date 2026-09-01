"""Pipeline unificado - integra todos os modulos."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from .config import config
from .database import UnifiedDatabase
from .metrics import GrantWatchMetrics, deve_notificar
from ..ml.classifier import RelevanceClassifier
from ..bot.bot import CognitiaBot

logger = logging.getLogger(__name__)

class CognitiaPipeline:
    """Pipeline completo: scrape -> dedup -> classify -> notify."""
    
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.db = UnifiedDatabase(config.DB_PATH)
        self.classifier = RelevanceClassifier(config.MODEL_PATH)
        self.metrics = GrantWatchMetrics(self.db)
        self.bot = None
        if token and chat_id:
            self.bot = CognitiaBot(token, chat_id, config.DB_PATH)
    
    async def executar(self) -> dict:
        """Executa pipeline completa uma vez."""
        stats = {
            'coletados': 0,
            'novos': 0,
            'inseridos': 0,
            'notificados': 0,
            'erros': 0,
            'inicio': datetime.now().isoformat()
        }
        
        try:
            # 1. Coletar de todas as fontes
            from ..scrapers.grants.finep import FinepScraper
            from ..scrapers.grants.cnpq import CnpqScraper
            from ..scrapers.grants.capes import CapesScraper
            from ..scrapers.artigos.arxiv import ArxivScraper
            from ..scrapers.gov.dou import DouScraper
            
            scrapers = [FinepScraper(), CnpqScraper(), CapesScraper(), ArxivScraper(), DouScraper()]
            
            todos_itens = []
            for scraper in scrapers:
                try:
                    itens = scraper.coletar()
                    for item in itens:
                        item['hash'] = self.db.hash_item(item['title'], item['url'])
                    todos_itens.extend(itens)
                    logger.info(f'[{scraper.nome}] Coletou {len(itens)} itens')
                except Exception as e:
                    logger.error(f'[{scraper.nome}] Erro: {e}')
                    stats['erros'] += 1
            
            stats['coletados'] = len(todos_itens)
            
            # 2. Dedup e insert
            novos = []
            for item in todos_itens:
                if self.db.insert_item(item):
                    novos.append(item)
            
            stats['novos'] = len(novos)
            stats['inseridos'] = len(novos)
            
            # 3. Classificar e notificar
            if novos and self.bot:
                for item in novos:
                    try:
                        label, confidence = self.classifier.prever(item['title'])
                        item['confidence'] = confidence
                        item['label'] = label
                        
                        deve, conf = deve_notificar(confidence, config.CONFIDENCE_MODE)
                        
                        if deve is True or deve is None:
                            await self.bot.notificar_item(item)
                            self.db.mark_notified(item['hash'])
                            stats['notificados'] += 1
                    except Exception as e:
                        logger.error(f'Erro ao processar item: {e}')
                        stats['erros'] += 1
            
            # 4. Verificar retreinamento
            self._verificar_retreinamento()
            
        except Exception as e:
            logger.error(f'Erro na pipeline: {e}')
            stats['erros'] += 1
        
        stats['fim'] = datetime.now().isoformat()
        logger.info(f'Pipeline finalizada: {stats}')
        return stats
    
    def _verificar_retreinamento(self):
        """Verifica se deve retreinar o modelo."""
        n_labels = self.db.count_labels()
        if n_labels >= 20 and n_labels % 20 == 0:
            logger.info(f'Retreinando modelo com {n_labels} labels...')
            try:
                labels_data = self.db.get_all_labels()
                if labels_data:
                    texts, labels = zip(*labels_data)
                    self.classifier.train(list(texts), list(labels))
                    self.classifier.save_model(config.MODEL_PATH)
                    logger.info('Modelo retreinado e salvo')
            except Exception as e:
                logger.error(f'Erro no retreinamento: {e}')

async def main():
    """Funcao principal para execucao via CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description='CognitiaBrain Pipeline')
    parser.add_argument('--run', action='store_true', help='Executa pipeline uma vez')
    parser.add_argument('--bot', action='store_true', help='Inicia bot em polling')
    parser.add_argument('--token', help='Telegram Bot Token')
    parser.add_argument('--chat-id', help='Telegram Chat ID')
    args = parser.parse_args()
    
    token = args.token or config.TELEGRAM_BOT_TOKEN
    chat_id = args.chat_id or config.TELEGRAM_CHAT_ID
    
    pipeline = CognitiaPipeline(token=token, chat_id=chat_id)
    
    if args.run:
        stats = await pipeline.executar()
        print(f'Estatisticas: {stats}')
    elif args.bot:
        await pipeline.bot.iniciar()
    else:
        parser.print_help()

if __name__ == '__main__':
    asyncio.run(main())
