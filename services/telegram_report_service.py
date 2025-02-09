# services/telegram_report_service.py

import logging
from datetime import datetime
from typing import Dict, Any
from telegram import Bot
from services.analytics_service import AnalyticsService
from config.settings import STATS_CHANNELS

logger = logging.getLogger(__name__)


class TelegramReportService:
    def __init__(self, bot: Bot, analytics_service: AnalyticsService):
        """
        Инициализация сервиса отчетов

        Args:
            bot: Экземпляр бота Telegram
            analytics_service: Сервис аналитики
        """
        self.bot = bot
        self.analytics = analytics_service

    async def send_daily_report(self, channel_id: str = None):
        """Отправка ежедневного отчета в канал"""
        try:
            # Получаем актуальную статистику из БД
            stats = self.analytics.get_daily_stats()
            report = self._format_daily_report(stats)
            channels = [channel_id] if channel_id else STATS_CHANNELS

            for channel in channels:
                try:
                    await self.bot.send_message(
                        chat_id=channel,
                        text=report,
                        parse_mode='Markdown'
                    )
                    logger.info(f"Daily report sent to channel {channel}")
                except Exception as e:
                    logger.error(f"Error sending daily report to channel {channel}: {e}")
        except Exception as e:
            logger.error(f"Error preparing daily report: {e}")

    async def send_weekly_report(self, stats: Dict[str, Any], channel_id: str = None):
        """Отправка еженедельного отчета"""
        try:
            report = self._format_weekly_report(stats)
            channels = [channel_id] if channel_id else STATS_CHANNELS

            for channel in channels:
                try:
                    await self.bot.send_message(
                        chat_id=channel,
                        text=report,
                        parse_mode='Markdown'
                    )
                    logger.info(f"Weekly report sent to channel {channel}")
                except Exception as e:
                    logger.error(f"Error sending weekly report to channel {channel}: {e}")
        except Exception as e:
            logger.error(f"Error preparing weekly report: {e}")

    def _format_daily_report(self, stats: Dict[str, Any]) -> str:
        """Форматирование ежедневного отчета"""
        report = [
            f"📊 *АНАЛИЗ ПРИМЕНЕНИЯ МЕТОДА ({stats['date']})*\n",

            "👥 *ПОЛЬЗОВАТЕЛИ*",
            f"• Всего уникальных: {stats['users']['total_unique']}",
            f"• Новых: {stats['users']['new_users']}",
            f"• Вернувшихся: {stats['users']['returning_users']}",
            f"• Активных: {stats['users']['active_users']}\n",

            "📈 *АКТИВНОСТЬ*",
            f"• Всего действий: {stats['engagement']['total_actions']}",
            self._format_command_usage(stats['engagement'].get('command_usage', {})),
            self._format_peak_hours(stats['engagement'].get('peak_hours', {})),

            "📚 *БАЗА ЗНАНИЙ*",
            self._format_knowledge_views(stats['content'].get('knowledge_base_views', {})),

            "🎯 *УПРАЖНЕНИЯ*",
            f"• Начато: {stats['exercises']['total_started']}",
            f"• Завершено: {stats['exercises']['total_completed']}",
            f"• Процент завершения: {stats['exercises'].get('completion_rate', 0):.1f}%"
        ]

        # Добавляем секцию с ошибками, только если они есть
        if stats['errors']['total_errors'] > 0:
            report.extend([
                "\n⚠️ *ОШИБКИ*",
                f"• Всего: {stats['errors']['total_errors']}",
                f"• Частота: {stats['errors'].get('error_rate', 0):.2f}%"
            ])

        return "\n".join(report)

    def _format_weekly_report(self, stats: Dict[str, Any]) -> str:
        """Форматирование еженедельного отчета"""
        report = [
            f"📊 *ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ ({stats.get('period', 'За неделю')})*\n",

            "👥 *ОБЩАЯ СТАТИСТИКА*",
            f"• Всего пользователей: {stats['users'].get('total_unique', 0)}",
            f"• Новых пользователей: {stats['users'].get('new_users', 0)}",
            f"• Активных пользователей: {stats['users'].get('active_users', 0)}\n",

            "📈 *АКТИВНОСТЬ*",
            f"• Всего действий: {stats['engagement'].get('total_actions', 0)}",
            f"• Среднее в день: {stats['engagement'].get('avg_daily_actions', 0):.1f}",

            "📊 *РЕЗУЛЬТАТЫ*",
            f"• Успешных консультаций: {stats['content'].get('completed_consultations', 0)}",
            f"• Выполнено упражнений: {stats['exercises'].get('total_completed', 0)}",
            f"• Процент завершения: {stats['exercises'].get('completion_rate', 0):.1f}%"
        ]

        return "\n".join(report)

    def _format_command_usage(self, command_usage: Dict[str, int]) -> str:
        """Форматирование статистики использования команд"""
        if not command_usage:
            return "• Нет данных по командам"

        commands = sorted(command_usage.items(), key=lambda x: x[1], reverse=True)[:5]
        return "• Топ команд:\n  " + "\n  ".join(
            f"{cmd}: {count}" for cmd, count in commands
        )

    def _format_peak_hours(self, peak_hours: Dict[int, int]) -> str:
        """Форматирование пиковых часов активности"""
        if not peak_hours:
            return "• Нет данных по часам активности"

        # Находим час с максимальной активностью
        max_hour = max(peak_hours.items(), key=lambda x: x[1])[0]
        return f"• Пик активности: {max_hour}:00-{(max_hour + 1):02d}:00"

    def _format_knowledge_views(self, views: Dict[str, int]) -> str:
        """Форматирование просмотров базы знаний"""
        if not views:
            return "• Нет данных по просмотрам"

        sections = sorted(views.items(), key=lambda x: x[1], reverse=True)
        return "• Популярные разделы:\n  " + "\n  ".join(
            f"{section}: {count}" for section, count in sections[:3]
        )
