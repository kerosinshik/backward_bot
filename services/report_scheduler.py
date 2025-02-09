# services/report_scheduler.py

import asyncio
from datetime import datetime, timedelta
import pytz
import logging

from config.settings import REPORT_SETTINGS, STATS_CHANNELS
from services.analytics_service import AnalyticsService
from services.telegram_report_service import TelegramReportService

logger = logging.getLogger(__name__)


class ReportScheduler:
    def __init__(self, bot, analytics_service: AnalyticsService):
        """
        Инициализация планировщика отчетов

        Args:
            bot: Экземпляр бота Telegram
            analytics_service: Сервис аналитики
        """
        self.bot = bot
        self.analytics = analytics_service
        self.report_service = TelegramReportService(bot, analytics_service)
        self.timezone = pytz.timezone(REPORT_SETTINGS['daily']['timezone'])
        self.is_running = False

    async def schedule_reports(self):
        """Запуск планировщика отчетов"""
        self.is_running = True
        logger.info("Report scheduler started")

        while self.is_running:
            try:
                now = datetime.now(self.timezone)
                current_time = now.strftime('%H:%M')

                # Проверяем ежедневные отчеты
                if current_time in REPORT_SETTINGS['daily']['times']:
                    logger.info(f"Sending daily reports at {current_time}")
                    for channel_id in STATS_CHANNELS:
                        await self.report_service.send_daily_report(channel_id)

                # Проверяем еженедельные отчеты
                if (now.weekday() in REPORT_SETTINGS['weekly']['days'] and
                        current_time == REPORT_SETTINGS['weekly']['time']):
                    logger.info(f"Sending weekly reports at {current_time}")
                    stats = self.analytics.get_daily_stats()  # Получаем статистику
                    for channel_id in STATS_CHANNELS:
                        await self.report_service.send_weekly_report(stats, channel_id)

                # Ждем 30 секунд перед следующей проверкой
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Error in report scheduler: {e}")
                await asyncio.sleep(60)  # В случае ошибки ждем дольше

    async def stop(self):
        """Остановка планировщика"""
        self.is_running = False
        logger.info("Report scheduler stopped")

    async def _check_channel_access(self, channel_id: str) -> bool:
        """Проверка доступа к каналу"""
        try:
            await self.bot.get_chat(channel_id)
            return True
        except Exception as e:
            logger.error(f"No access to channel {channel_id}: {e}")
            return False
