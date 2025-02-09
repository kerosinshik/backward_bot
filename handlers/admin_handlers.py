# handlers/admin_handlers.py

from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.settings import ADMIN_USERS
from services.analytics_service import AnalyticsService
from services.telegram_report_service import TelegramReportService
import logging
from database.models import ExerciseFeedback

logger = logging.getLogger(__name__)

async def verify_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id in ADMIN_USERS

class AdminCommands:
    """Класс для обработки административных команд"""

    def __init__(self, analytics_service: AnalyticsService, report_service: TelegramReportService):
        self.analytics = analytics_service
        self.report_service = report_service

    async def verify_admin(self, user_id: int) -> bool:
        """Проверка прав администратора"""
        return user_id in ADMIN_USERS

    async def handle_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик административных команд"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id

        if not await self.verify_admin(user_id):
            await update.message.reply_text("У вас нет прав для выполнения этой команды.")
            return

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
            elif command == '/feedbacks':  # Добавляем новую команду
                await self.handle_feedbacks_command(update, context)
            elif command == '/export_feedbacks':
                await self.handle_feedbacks_export(update, context)
        except Exception as e:
            await update.message.reply_text(f"Ошибка при выполнении команды: {str(e)}")

    async def send_general_stats(self, update: Update):
        """Отправка общей статистики"""
        stats = self.analytics.get_daily_stats()  # Получаем статистику за текущий день
        total_users = stats['users']['total_unique']
        total_actions = stats['engagement']['total_actions']

        message = [
            "📊 *ОБЩАЯ СТАТИСТИКА*\n",
            f"👥 *Пользователи*: {total_users}",
            f"📝 *Действия*: {total_actions}",
            f"🎯 *Упражнения начато*: {stats['exercises']['total_started']}",
            f"✅ *Упражнения завершено*: {stats['exercises']['total_completed']}",
            f"\n🔄 *Конверсия упражнений*: {stats['exercises'].get('completion_rate', 0):.1f}%"
        ]

        await update.message.reply_text("\n".join(message), parse_mode='Markdown')

    async def send_daily_stats(self, update: Update):
        """Отправка ежедневной статистики"""
        stats = self.analytics.get_daily_stats()
        await self.report_service.send_daily_report(stats)
        await update.message.reply_text("Ежедневный отчет сформирован и отправлен в канал статистики.")

    async def send_weekly_stats(self, update: Update):
        """Отправка еженедельной статистики"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)

        message = [
            f"📊 *СТАТИСТИКА ЗА НЕДЕЛЮ*\n",
            f"Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}\n"
        ]

        weekly_totals = {
            'users': 0,
            'actions': 0,
            'exercises_started': 0,
            'exercises_completed': 0
        }

        # Собираем статистику по дням
        current_date = start_date
        while current_date <= end_date:
            daily_stats = self.analytics.get_daily_stats(current_date)
            weekly_totals['users'] += daily_stats['users']['total_unique']
            weekly_totals['actions'] += daily_stats['engagement']['total_actions']
            weekly_totals['exercises_started'] += daily_stats['exercises']['total_started']
            weekly_totals['exercises_completed'] += daily_stats['exercises']['total_completed']
            current_date += timedelta(days=1)

        message.extend([
            f"👥 *Всего пользователей*: {weekly_totals['users']}",
            f"📝 *Всего действий*: {weekly_totals['actions']}",
            f"🎯 *Упражнений начато*: {weekly_totals['exercises_started']}",
            f"✅ *Упражнений завершено*: {weekly_totals['exercises_completed']}"
        ])

        await update.message.reply_text("\n".join(message), parse_mode='Markdown')

    async def send_users_stats(self, update: Update):
        """Отправка статистики по пользователям"""
        stats = self.analytics.get_daily_stats()

        message = [
            "👥 *СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ*\n",
            f"*Сегодня*:",
            f"• Всего уникальных: {stats['users']['total_unique']}",
            f"• Новых: {stats['users']['new_users']}",
            f"• Вернувшихся: {stats['users']['returning_users']}",
            f"• Активных: {stats['users']['active_users']}\n",
            "*Активность*:",
            f"• Среднее количество действий: {stats['engagement']['total_actions'] / max(stats['users']['total_unique'], 1):.1f}",
            "\n*Популярные разделы*:"
        ]

        for section, count in stats['content'].get('knowledge_base_views', {}).items():
            message.append(f"• {section}: {count}")

        await update.message.reply_text("\n".join(message), parse_mode='Markdown')

    async def send_error_stats(self, update: Update):
        """Отправка статистики ошибок"""
        stats = self.analytics.get_daily_stats()

        message = [
            "⚠️ *СТАТИСТИКА ОШИБОК*\n",
            f"• Всего ошибок: {stats['errors']['total_errors']}",
            f"• Частота ошибок: {stats['errors'].get('error_rate', 0):.2f}%\n",
            "*Типы ошибок*:"
        ]

        for error_type, count in stats['errors'].get('error_types', {}).items():
            message.append(f"• {error_type}: {count}")

        await update.message.reply_text("\n".join(message), parse_mode='Markdown')

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback-запросов от админских кнопок"""
        query = update.callback_query
        await query.answer()

        if not await self.verify_admin(query.from_user.id):
            await query.message.reply_text("У вас нет прав для выполнения этой команды.")
            return

        callback_data = query.data

        try:
            if callback_data == "admin_stats_daily":
                await self.send_daily_stats(update)
            elif callback_data == "admin_stats_weekly":
                await self.send_weekly_stats(update)
            elif callback_data == "admin_stats_users":
                await self.send_users_stats(update)
            elif callback_data == "admin_stats_errors":
                await self.send_error_stats(update)
        except Exception as e:
            await query.message.reply_text(f"Ошибка при обработке запроса: {str(e)}")

    async def handle_feedbacks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /feedbacks"""
        try:
            session = context.bot_data['db_session']
            feedbacks = session.query(ExerciseFeedback).order_by(ExerciseFeedback.feedback_date.desc()).all()

            if not feedbacks:
                await update.message.reply_text("Пока нет отзывов об упражнениях.")
                return

            response = "📝 Последние отзывы об упражнениях:\n\n"
            for fb in feedbacks:
                # Получаем информацию о пользователе
                try:
                    user = await context.bot.get_chat(fb.user_id)
                    user_info = f"@{user.username}" if user.username else f"id: {fb.user_id}"
                    user_name = user.full_name
                except Exception:
                    user_info = f"id: {fb.user_id}"
                    user_name = "Неизвестный пользователь"

                response += f"Дата: {fb.feedback_date.strftime('%Y-%m-%d %H:%M')}\n"
                response += f"Пользователь: {user_name} ({user_info})\n"
                response += f"Упражнение: {fb.exercise_id}\n"
                response += f"Отзыв: {fb.feedback_text}\n"
                response += "-" * 20 + "\n"

            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error getting feedbacks: {e}")
            await update.message.reply_text("Произошла ошибка при получении отзывов.")

    async def handle_feedbacks_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /export_feedbacks"""
        try:
            session = context.bot_data['db_session']
            feedbacks = session.query(ExerciseFeedback).order_by(ExerciseFeedback.feedback_date.desc()).all()

            if not feedbacks:
                await update.message.reply_text("Пока нет отзывов для выгрузки.")
                return

            # Создаем CSV в памяти
            import io
            import csv
            from datetime import datetime

            output = io.StringIO()
            writer = csv.writer(output, delimiter=';', quotechar='"')

            # Записываем заголовки
            writer.writerow(['Дата', 'User ID', 'Username', 'Имя', 'Упражнение', 'Отзыв', 'Контекст'])

            # Записываем данные
            for fb in feedbacks:
                try:
                    user = await context.bot.get_chat(fb.user_id)
                    username = f"@{user.username}" if user.username else "Нет"
                    user_name = user.full_name
                except Exception:
                    username = "Недоступен"
                    user_name = "Неизвестный пользователь"

                writer.writerow([
                    fb.feedback_date.strftime('%Y-%m-%d %H:%M'),
                    fb.user_id,
                    username,
                    user_name,
                    fb.exercise_id,
                    fb.feedback_text,
                    fb.context
                ])

            # Создаем файл для отправки
            output.seek(0)
            filename = f"feedbacks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

            # Отправляем файл
            await update.message.reply_document(
                document=io.BytesIO(output.getvalue().encode('utf-8-sig')),
                # utf-8-sig для корректного отображения в Excel
                filename=filename,
                caption="Выгрузка отзывов об упражнениях"
            )

        except Exception as e:
            logger.error(f"Error exporting feedbacks: {e}")
            await update.message.reply_text("Произошла ошибка при выгрузке отзывов.")
