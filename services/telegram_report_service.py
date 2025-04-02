# services/telegram_report_service.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from services.analytics_service import AnalyticsService
from services.user_history_service import UserHistoryService
from config.settings import (
    STATS_CHANNELS,
    ANONYMIZATION_SETTINGS,
    REPORT_SETTINGS
)

logger = logging.getLogger(__name__)


class TelegramReportService:
    """
    Сервис для создания и отправки отчетов с учетом конфиденциальности
    """

    def __init__(
            self,
            bot: Bot,
            analytics_service: AnalyticsService,
            user_history_service: Optional[UserHistoryService] = None
    ):
        """
        Инициализация сервиса репортов

        Args:
            bot: Экземпляр бота Telegram
            analytics_service: Сервис аналитики
            user_history_service: Сервис истории пользователей
        """
        self.bot = bot
        self.analytics = analytics_service
        self.user_history = user_history_service

        # Настройки конфиденциальности
        self.pseudonymize = ANONYMIZATION_SETTINGS.get(
            'enable_pseudonymization',
            True
        )

    async def send_daily_report(
            self,
            channel_id: Optional[str] = None,
            stats: Optional[Dict[str, Any]] = None
    ):
        """
        Отправка ежедневного отчета с учетом конфиденциальности

        Args:
            channel_id: ID канала для отправки (опционально)
            stats: Предварительно подготовленная статистика (опционально)
        """
        try:
            # Получаем статистику, если не передана
            if not stats:
                stats = self.analytics.get_daily_stats()

            # Формируем отчет
            report = self._format_daily_report(stats)

            # Определяем каналы для отправки
            channels = [channel_id] if channel_id else STATS_CHANNELS

            # Отправляем в каждый канал
            for channel in channels:
                try:
                    await self._safe_send_message(channel, report)
                except Exception as e:
                    logger.error(f"Error sending daily report to channel {channel}: {e}")

        except Exception as e:
            logger.error(f"Error preparing daily report: {e}")

    async def send_weekly_report(
            self,
            stats: Optional[Dict[str, Any]] = None,
            channel_id: Optional[str] = None
    ):
        """
        Отправка еженедельного отчета с учетом конфиденциальности

        Args:
            stats: Предварительно подготовленная статистика (опционально)
            channel_id: ID канала для отправки (опционально)
        """
        try:
            # Получаем статистику за неделю
            if not stats:
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=7)
                stats = self._aggregate_weekly_stats(start_date, end_date)

            # Формируем отчет
            report = self._format_weekly_report(stats)

            # Определяем каналы для отправки
            channels = [channel_id] if channel_id else STATS_CHANNELS

            # Отправляем в каждый канал
            for channel in channels:
                try:
                    await self._safe_send_message(channel, report)
                except Exception as e:
                    logger.error(f"Error sending weekly report to channel {channel}: {e}")

        except Exception as e:
            logger.error(f"Error preparing weekly report: {e}")

    def _format_daily_report(self, stats: Dict[str, Any]) -> str:
        """
        Форматирование ежедневного отчета с учетом конфиденциальности

        Args:
            stats: Статистика за день

        Returns:
            Отформатированный текст отчета
        """
        try:
            # Базовый шаблон отчета
            report = [
                f"📊 *АНАЛИЗ СИСТЕМЫ ({stats.get('date', 'Сегодня')})*\n",

                "👥 *ПОЛЬЗОВАТЕЛИ*",
                f"• Всего уникальных: {stats['users'].get('total_unique', 0)}",
                f"• Новых: {stats['users'].get('new_users', 0)}",
                f"• Вернувшихся: {stats['users'].get('returning_users', 0)}",
                f"• Активных: {stats['users'].get('active_users', 0)}\n",

                "📈 *АКТИВНОСТЬ*",
                f"• Всего действий: {stats['engagement'].get('total_actions', 0)}",
                self._format_command_usage(stats['engagement'].get('command_usage', {})),
                self._format_peak_hours(stats['engagement'].get('peak_hours', {}))
            ]

            # Консультации (если есть)
            if stats.get('consultations'):
                report.extend([
                    "\n🗣️ *КОНСУЛЬТАЦИИ*",
                    f"• Всего консультаций: {stats['consultations'].get('total_consultations', 0)}",
                    f"• Средняя длина: {stats['consultations'].get('consultation_length', {}).get('avg_length', 0):.1f} символов"
                ])

            # Ошибки (если есть)
            if stats.get('errors', {}).get('total_errors', 0) > 0:
                report.extend([
                    "\n⚠️ *ОШИБКИ*",
                    f"• Всего: {stats['errors'].get('total_errors', 0)}",
                    f"• Частота: {stats['errors'].get('error_rate', 0):.2f}%"
                ])

            return "\n".join(report)

        except Exception as e:
            logger.error(f"Error formatting daily report: {e}")
            return "📊 Ошибка при формировании ежедневного отчета"

    def _format_weekly_report(self, stats: Dict[str, Any]) -> str:
        """
        Форматирование еженедельного отчета с учетом конфиденциальности

        Args:
            stats: Статистика за неделю

        Returns:
            Отформатированный текст отчета
        """
        try:
            # Базовый шаблон недельного отчета
            report = [
                f"📊 *ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ* ({stats.get('period', 'За неделю')})\n",

                "👥 *ПОЛЬЗОВАТЕЛИ*",
                f"• Всего: {stats.get('total_users', 0)}",
                f"• Новых: {stats.get('new_users', 0)}",
                f"• Активных: {stats.get('active_users', 0)}\n",

                "📈 *АКТИВНОСТЬ*",
                f"• Всего действий: {stats.get('total_actions', 0)}",
                f"• В среднем в день: {stats.get('avg_daily_actions', 0):.1f}\n"
            ]

            # Консультации
            if stats.get('consultations'):
                report.extend([
                    "🗣️ *КОНСУЛЬТАЦИИ*",
                    f"• Всего: {stats['consultations'].get('total', 0)}",
                    f"• Завершенных: {stats['consultations'].get('completed', 0)}",
                    f"• Средняя длина: {stats['consultations'].get('avg_length', 0):.1f} сообщений"
                ])

            # Ошибки
            if stats.get('errors'):
                report.extend([
                    "\n⚠️ *ОШИБКИ*",
                    f"• Всего: {stats['errors'].get('total_errors', 0)}",
                    f"• Частота: {stats['errors'].get('error_rate', 0):.2f}%"
                ])

            return "\n".join(report)

        except Exception as e:
            logger.error(f"Error formatting weekly report: {e}")
            return "📊 Ошибка при формировании еженедельного отчета"

    def _aggregate_weekly_stats(
            self,
            start_date: datetime,
            end_date: datetime
    ) -> Dict[str, Any]:
        """
        Агрегация статистики за неделю

        Args:
            start_date: Начало недели
            end_date: Конец недели

        Returns:
            Агрегированная статистика
        """
        # Получаем статистику по дням и агрегируем
        weekly_stats = {
            'period': f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}",
            'total_users': 0,
            'new_users': 0,
            'active_users': 0,
            'total_actions': 0,
            'avg_daily_actions': 0,
            'consultations': {
                'total': 0,
                'completed': 0,
                'avg_length': 0
            },
            'errors': {
                'total_errors': 0,
                'error_rate': 0
            }
        }

        # Собираем статистику по дням
        days_count = 0
        current_date = start_date
        while current_date <= end_date:
            try:
                daily_stats = self.analytics.get_daily_stats(current_date)

                # Агрегируем пользователей
                weekly_stats['total_users'] += daily_stats['users'].get('total_unique', 0)
                weekly_stats['new_users'] += daily_stats['users'].get('new_users', 0)
                weekly_stats['active_users'] += daily_stats['users'].get('active_users', 0)

                # Агрегируем действия
                weekly_stats['total_actions'] += daily_stats['engagement'].get('total_actions', 0)

                # Агрегируем консультации
                weekly_stats['consultations']['total'] += daily_stats.get('consultations', {}).get('total_consultations', 0)

                # Агрегируем ошибки
                weekly_stats['errors']['total_errors'] += daily_stats.get('errors', {}).get('total_errors', 0)

                days_count += 1
                current_date += timedelta(days=1)

            except Exception as e:
                logger.error(f"Error processing daily stats for {current_date}: {e}")
                continue

        # Вычисляем средние значения
        if days_count > 0:
            weekly_stats['avg_daily_actions'] = weekly_stats['total_actions'] / days_count
            weekly_stats['errors']['error_rate'] = (
                                                           weekly_stats['errors']['total_errors'] / (
                                                               weekly_stats['total_actions'] or 1)
                                                   ) * 100

        return weekly_stats

    def _format_command_usage(self, command_usage: Dict[str, Any]) -> str:
        """
        Форматирование статистики использования команд

        Args:
            command_usage: Статистика использования команд

        Returns:
            Отформатированный текст
        """
        if not command_usage:
            return "• Нет данных по командам"

        try:
            # Сортируем команды по количеству использований
            sorted_commands = sorted(
                command_usage.items(),
                key=lambda x: x[1].get('total_usage', 0),
                reverse=True
            )

            # Форматируем топ-5 команд
            command_lines = [
                f"• {cmd}: {stats.get('total_usage', 0)} (пользователей: {stats.get('unique_users', 0)})"
                for cmd, stats in sorted_commands[:5]
            ]

            return "• Топ команд:\n" + "\n".join(command_lines)

        except Exception as e:
            logger.error(f"Error formatting command usage: {e}")
            return "• Нет данных по командам"

    def _format_peak_hours(self, peak_hours: Dict[str, Any]) -> str:
        """
        Форматирование статистики пиковых часов

        Args:
            peak_hours: Статистика активности по часам

        Returns:
            Отформатированный текст
        """
        if not peak_hours:
            return "• Нет данных по часам активности"

        try:
            # Находим час с максимальной активностью
            max_hour_stats = max(
                peak_hours.items(),
                key=lambda x: x[1].get('total_actions', 0)
            )

            return (
                f"• Пик активности: {max_hour_stats[0]}:00-{int(max_hour_stats[0]) + 1}:00 "
                f"(действий: {max_hour_stats[1].get('total_actions', 0)})"
            )

        except Exception as e:
            logger.error(f"Error formatting peak hours: {e}")
            return "• Нет данных по часам активности"

    async def _safe_send_message(self, channel_id: str, message: str):
        """
        Безопасная отправка сообщения с обработкой ошибок

        Args:
            channel_id: ID канала
            message: Текст сообщения
        """
        try:
            await self.bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            logger.info(f"Report sent successfully to channel {channel_id}")

        except TelegramError as e:
            logger.error(f"Telegram error sending report to {channel_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending report to {channel_id}: {e}")
