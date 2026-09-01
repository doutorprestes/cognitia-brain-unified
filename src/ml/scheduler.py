"""Scheduler - agendamento de tarefas."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..shared.config import config

logger = logging.getLogger(__name__)

class TaskScheduler:
    """Agendador de tarefas do sistema."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
    
    def start(self):
        self.scheduler.start()
    
    def stop(self):
        self.scheduler.shutdown()
    
    def adicionar_scrape(self, func, interval_minutes: int = 360):
        """Adiciona tarefa de scrape periodica."""
        self.scheduler.add_job(
            func,
            IntervalTrigger(minutes=interval_minutes),
            id='scrape_grants',
            name='Scrape Grants'
        )
    
    def adicionar_digest(self, func, hour: int = 8, minute: int = 0):
        """Adiciona tarefa de digest semanal."""
        self.scheduler.add_job(
            func,
            CronTrigger(day_of_week='mon', hour=hour, minute=minute),
            id='weekly_digest',
            name='Weekly Digest'
        )
    
    def adicionar_retreinamento(self, func, interval_hours: int = 24):
        """Adiciona tarefa de retreinamento periodico."""
        self.scheduler.add_job(
            func,
            IntervalTrigger(hours=interval_hours),
            id='retrain',
            name='Retreinamento'
        )
