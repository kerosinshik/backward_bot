# handlers/admin_handlers.py
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext

from config.settings import (
    ADMIN_USERS,
    ANONYMIZATION_SETTINGS,
    ANALYTICS_SETTINGS
)
from services.analytics_service import AnalyticsService
from services.user_history_service import UserHistoryService
from services.telegram_report_service import TelegramReportService

logger = logging.getLogger(__name__)


class AdminCommands:
    """Класс для обработки административных команд с учетом конфиденциальности"""

    def __init__(
            self,
            analytics_service: AnalyticsService,
            report_service: TelegramReportService,
            user_history_service: UserHistoryService
    ):
        """
        Инициализация административных команд

        Args:
            analytics_service: Сервис аналитики
            report_service: Сервис telegram-репортов
            user_history_service: Сервис истории пользователей
        """
        self.analytics = analytics_service
        self.report_service = report_service
        self.user_history = user_history_service

        # Настройки конфиденциальности
        self.pseudonymize = ANONYMIZATION_SETTINGS.get(
            'enable_pseudonymization',
            True
        )

    async def verify_admin(self, user_id: int) -> bool:
        """
        Проверка прав администратора

        Args:
            user_id: ID пользователя

        Returns:
            bool: Является ли пользователь администратором
        """
        return user_id in ADMIN_USERS

    async def handle_admin_command(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Обработчик административных команд с учетом конфиденциальности

        Args:
            update: Входящее обновление
            context: Контекст выполнения
        """
        if not update.effective_user:
            return

        user_id = update.effective_user.id

        # Проверка прав администратора
        if not await self.verify_admin(user_id):
            await update.message.reply_text(
                "У вас нет прав для выполнения этой команды."
            )
            return

        # Получаем команду
        command = update.message.text.split()[0].lower()

        try:
            if command == '/stats':
                await self.send_general_stats(update)
            elif command == '/daily':
                await self.send_daily_stats(update)
            elif command == '/weekly':
                await self.send_weekly_stats(update)
            elif command == '/users':
                await self.send_users_stats(update)
            elif command == '/errors':
                await self.send_error_stats(update)
            elif command == '/privacy_stats':
                await self.send_privacy_stats(update)

        except Exception as e:
            logger.error(f"Error in admin command {command}: {e}")
            await update.message.reply_text(
                f"Произошла ошибка при выполнении команды: {str(e)}"
            )

    async def send_general_stats(self, update: Update):
        """
        Отправка общей статистики с учетом конфиденциальности

        Args:
            update: Входящее обновление
        """
        logger.info("Entering send_general_stats method")
        # Получаем статистику за текущий день
        stats = self.analytics.get_daily_stats()

        logger.info(f"Obtained stats: {stats}")

        total_users = stats['users']['total_unique']
        total_actions = stats['engagement']['total_actions']

        message = [
            "📊 *ОБЩАЯ СТАТИСТИКА*\n",
            f"👥 *Пользователи*: {total_users}",
            f"📝 *Действия*: {total_actions}",
            "\n*Настройки конфиденциальности*:",
            f"• Псевдонимизация: {'Включена' if self.pseudonymize else 'Выключена'}"
        ]

        await update.message.reply_text(
            "\n".join(message),
            parse_mode='Markdown'
        )

    async def send_daily_stats(self, update: Update):
        """
        Отправка ежедневной статистики

        Args:
            update: Входящее обновление
        """
        # Получаем статистику
        stats = self.analytics.get_daily_stats()

        # Отправляем отчет через сервис репортов
        await self.report_service.send_daily_report(stats=stats)

        await update.message.reply_text(
            "Ежедневный отчет сформирован и отправлен в канал статистики."
        )

    async def send_weekly_stats(self, update: Update):
        """
        Отправка еженедельной статистики

        Args:
            update: Входящее обновление
        """
        # Вычисляем период
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)

        # Получаем агрегированную статистику
        weekly_stats = self.report_service._aggregate_weekly_stats(start_date, end_date)

        # Формируем сообщение
        message = [
            f"📊 *СТАТИСТИКА ЗА НЕДЕЛЮ*\n",
            f"Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}\n",
            f"👥 *Всего пользователей*: {weekly_stats['total_users']}",
            f"📝 *Всего действий*: {weekly_stats['total_actions']}",
            f"📊 *Новых пользователей*: {weekly_stats['new_users']}",
            f"🔄 *Активных пользователей*: {weekly_stats['active_users']}"
        ]

        # Отправляем отчет через сервис репортов
        await self.report_service.send_weekly_report(stats=weekly_stats)

        # Отправляем summary в чат администратора
        await update.message.reply_text(
            "\n".join(message),
            parse_mode='Markdown'
        )

    async def send_users_stats(self, update: Update):
        """
        Отправка статистики по пользователям

        Args:
            update: Входящее обновление
        """
        # Получаем статистику
        stats = self.analytics.get_daily_stats()

        message = [
            "👥 *СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ*\n",
            f"*Сегодня*:",
            f"• Всего уникальных: {stats['users']['total_unique']}",
            f"• Новых: {stats['users']['new_users']}",
            f"• Вернувшихся: {stats['users']['returning_users']}",
            f"• Активных: {stats['users']['active_users']}\n",
            "*Активность*:",
            f"• Среднее количество действий: {stats['engagement']['total_actions'] / max(stats['users']['total_unique'], 1):.1f}"
        ]

        await update.message.reply_text(
            "\n".join(message),
            parse_mode='Markdown'
        )

    async def send_error_stats(self, update: Update):
        """
        Отправка статистики ошибок

        Args:
            update: Входящее обновление
        """
        # Получаем статистику
        stats = self.analytics.get_daily_stats()

        message = [
            "⚠️ *СТАТИСТИКА ОШИБОК*\n",
            f"• Всего ошибок: {stats['errors']['total_errors']}",
            f"• Частота ошибок: {stats['errors'].get('error_rate', 0):.2f}%"
        ]

        # Добавляем типы ошибок
        if stats['errors'].get('error_types'):
            message.append("\n*Типы ошибок*:")
            for error_type, count in stats['errors']['error_types'].items():
                message.append(f"• {error_type}: {count}")

        await update.message.reply_text(
            "\n".join(message),
            parse_mode='Markdown'
        )

    async def send_privacy_stats(self, update: Update):
        """
        Отправка статистики по конфиденциальности

        Args:
            update: Входящее обновление
        """
        # Получаем статистику управления данными
        try:
            # Используем сервис истории пользователей
            privacy_stats = await self.user_history.get_data_retention_statistics()

            message = [
                "🔒 *СТАТИСТИКА КОНФИДЕНЦИАЛЬНОСТИ*\n",
                f"*Настройки*:",
                f"• Псевдонимизация: {'Включена' if self.pseudonymize else 'Выключена'}",
                f"• Максимальная длина контекста: {ANALYTICS_SETTINGS.get('max_context_messages', 30)} сообщений\n",
                "*Управление данными*:",
                f"• Всего операций очистки: {privacy_stats.get('total_operations', 0)}",
                f"• Всего затронутых записей: {privacy_stats.get('total_records_affected', 0)}"
            ]

            # Добавляем статистику по типам операций
            if privacy_stats.get('operations_by_type'):
                message.append("\n*Типы операций*:")
                for op_type, data in privacy_stats['operations_by_type'].items():
                    message.append(
                        f"• {op_type}: "
                        f"{data.get('count', 0)} операций, "
                        f"{data.get('records_affected', 0)} записей"
                    )

            # Информация за последний месяц
            last_month = privacy_stats.get('last_30_days', {})
            message.extend([
                "\n*За последние 30 дней*:",
                f"• Операций: {last_month.get('operations', 0)}",
                f"• Удалено записей: {last_month.get('records_affected', 0)}"
            ])

            # Последняя операция
            if privacy_stats.get('last_operation_date'):
                message.append(
                    f"\n*Последняя операция*: {privacy_stats['last_operation_date']}"
                )

            await update.message.reply_text(
                "\n".join(message),
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"Error getting privacy stats: {e}")
            await update.message.reply_text(
                "Не удалось получить статистику конфиденциальности."
            )

    async def handle_admin_callback(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Обработчик callback-запросов от администраторов

        Args:
            update: Входящее обновление
            context: Контекст выполнения
        """
        query = update.callback_query
        await query.answer()

        # Проверяем права администратора
        if not await self.verify_admin(query.from_user.id):
            await query.message.reply_text(
                "У вас нет прав для выполнения этой команды."
            )
            return

        try:
            # Обработка различных callback-запросов
            callback_data = query.data

            if callback_data == "admin_stats_daily":
                await self.send_daily_stats(update)
            elif callback_data == "admin_stats_weekly":
                await self.send_weekly_stats(update)
            elif callback_data == "admin_stats_users":
                await self.send_users_stats(update)
            elif callback_data == "admin_stats_errors":
                await self.send_error_stats(update)
            elif callback_data == "admin_stats_privacy":
                await self.send_privacy_stats(update)

        except Exception as e:
            logger.error(f"Error in admin callback: {e}")
            await query.message.reply_text(
                f"Произошла ошибка при обработке запроса: {str(e)}"
            )
