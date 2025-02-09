import logging
from telegram.ext import ApplicationBuilder, Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config.settings import TELEGRAM_BOT_TOKEN, DATABASE_URL, ADMIN_USERS
from handlers.message_handlers import (
    start_command,
    help_command,
    new_consultation_command,
    support_command,
    handle_message,
    handle_callback_query,
    handle_exercise,
    knowledge_command,
    principle_command
)
from handlers.admin_handlers import AdminCommands
from services.analytics_service import AnalyticsService
from services.telegram_report_service import TelegramReportService
from database.models import Base

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def setup_database():
    """Настройка базы данных"""
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def setup_application() -> Application:
    """Настройка приложения"""
    # Создаем приложение
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Инициализируем базу данных
    db_session = setup_database()
    application.bot_data['db_session'] = db_session

    # Инициализируем сервисы
    analytics_service = AnalyticsService(db_session)
    report_service = TelegramReportService(application.bot, analytics_service)
    admin_commands = AdminCommands(analytics_service, report_service)

    # Основные команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new", new_consultation_command))
    application.add_handler(CommandHandler("support", support_command))

    # Команды базы знаний
    for cmd in ["principles", "examples", "faq", "practice"]:
        application.add_handler(CommandHandler(cmd, knowledge_command))

    # Принципы
    for i in range(1, 4):
        application.add_handler(
            CommandHandler(
                f"principle{i}",
                lambda update, context, num=i: principle_command(update, context, str(num))
            )
        )

    # Упражнения
    for i in range(1, 3):
        application.add_handler(
            CommandHandler(
                f"exercise{i}",
                lambda update, context, num=i: handle_exercise(update, context, str(num))
            )
        )

    # Админские команды
    admin_command_list = ["stats", "daily", "weekly", "users", "errors", "feedbacks", "export_feedbacks"]
    application.add_handler(
        CommandHandler(
            admin_command_list,
            admin_commands.handle_admin_command,
            filters.User(user_id=ADMIN_USERS)
        )
    )

    # Callback запросы
    application.add_handler(
        CallbackQueryHandler(
            admin_commands.handle_admin_callback,
            pattern="^admin_.*"
        )
    )
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Текстовые сообщения
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    return application


def main():
    """Запуск бота"""
    try:
        logger.info("Starting Reverse Movement Method consultant bot...")
        application = setup_application()
        application.run_polling()

    except Exception as e:
        logger.error(f"Error running bot: {e}")
    finally:
        # Закрываем соединение с БД при выходе
        if 'application' in locals():
            if 'db_session' in application.bot_data:
                application.bot_data['db_session'].close()
        logger.info("Bot stopped")


if __name__ == '__main__':
    main()
