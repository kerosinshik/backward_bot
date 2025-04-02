import asyncio
import logging
from pathlib import Path
import os
import sys
from datetime import datetime
import signal
import aiohttp
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

from config.settings import (
    TELEGRAM_BOT_TOKEN,
    DATABASE_URL,
    ADMIN_USERS,
    WEBHOOK_PORT,
    WEBHOOK_HOST,
    WEBHOOK_PATH,
    WEBHOOK_LISTEN
)
from database.models import Base
from handlers.message_handlers import (
    start_command,
    help_command,
    new_consultation_command,
    handle_message,
    handle_callback_query,
    knowledge_command,
    privacy_command,
    handle_feedback,
    handle_data_request,
    handle_data_deletion,
    handle_data_callbacks
)
from handlers.admin_handlers import AdminCommands
from services.analytics_service import AnalyticsService
from services.user_history_service import UserHistoryService
from services.telegram_report_service import TelegramReportService
from services.report_scheduler import ReportScheduler
from handlers.promo_code_handlers import (
    handle_promo_command,
    handle_create_promo_command,
    handle_disable_promo_command,
    handle_promostat_command
)
from handlers.payment_menu_handlers import (
    handle_balance_command,
    handle_pricing_command,
    handle_payment_callback
)
# Добавляем импорт обработчика webhook ЮKassa
from handlers.yookassa_webhook_handler import YooKassaWebhookHandler, setup_webhook_routes
from services.payment_service import PaymentService

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Убедимся, что директория для логов существует
log_dir = Path("./logs")
log_dir.mkdir(exist_ok=True)

# Настройка файла лога
file_handler = logging.FileHandler(log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)


def setup_application() -> Application:
    """Настройка приложения Telegram бота"""
    # Инициализация базы данных
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Инициализация приложения
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Сохраняем сессию в контексте приложения
    application.bot_data["db_session"] = session

    # Инициализация сервисов аналитики и отчетов
    analytics_service = AnalyticsService(session)
    user_history_service = UserHistoryService(session)
    report_service = TelegramReportService(application.bot, analytics_service, user_history_service)

    # Инициализация административных команд
    admin_commands = AdminCommands(analytics_service, report_service, user_history_service)

    # Инициализация сервиса платежей для webhook
    payment_service = PaymentService(session)

    # Инициализация обработчика webhook
    webhook_handler = YooKassaWebhookHandler(application.bot, payment_service)

    # Сохраняем обработчик webhook в контексте приложения
    application.bot_data["webhook_handler"] = webhook_handler

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new", new_consultation_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("mydata", handle_data_request))
    application.add_handler(CommandHandler("deletedata", handle_data_deletion))

    # Регистрация обработчиков административных команд
    application.add_handler(
        CommandHandler(
            ["stats", "daily", "weekly", "users", "errors", "privacy_stats"],
            admin_commands.handle_admin_command,
            filters.User(user_id=ADMIN_USERS)
        )
    )

    # Регистрация обработчика для команды базы знаний
    application.add_handler(CommandHandler(
        ["principles", "faq", "principle1", "principle2", "principle3", "principle4"],
        knowledge_command
    ))

    # Регистрация обработчиков платежей
    application.add_handler(CommandHandler("balance", handle_balance_command))
    application.add_handler(CommandHandler("pricing", handle_pricing_command))

    # Регистрация обработчиков промокодов
    application.add_handler(CommandHandler("promo", handle_promo_command))

    # Административные команды для промокодов
    application.add_handler(
        CommandHandler(
            "createpromo",
            handle_create_promo_command,
            filters.User(user_id=ADMIN_USERS)
        )
    )
    application.add_handler(
        CommandHandler(
            "disablepromo",
            handle_disable_promo_command,
            filters.User(user_id=ADMIN_USERS)
        )
    )
    application.add_handler(
        CommandHandler(
            "promostat",
            handle_promostat_command,
            filters.User(user_id=ADMIN_USERS)
        )
    )

    # ВАЖНО: Порядок регистрации обработчиков callback имеет значение
    # Сначала регистрируем специфические обработчики

    # Обработчик callback-запросов для платежей (должен идти первым)
    application.add_handler(
        CallbackQueryHandler(
            handle_payment_callback,
            pattern="^(show_tariffs|select_plan:|activate_trial|create_payment:|check_payment:|payment_success:|check_payment|cancel_payment|credits_history|show_balance).*$"
        )
    )

    # Обработчик для данных (должен идти вторым)
    application.add_handler(
        CallbackQueryHandler(
            handle_data_callbacks,
            pattern="^(confirm_delete_data|cancel_delete_data|anonymize_data)$"
        )
    )

    # Обработчик для административных команд (должен идти третьим)
    application.add_handler(
        CallbackQueryHandler(
            admin_commands.handle_admin_callback,
            pattern="^admin_.*$"
        )
    )

    # Общий обработчик callback (должен идти последним)
    application.add_handler(
        CallbackQueryHandler(handle_callback_query)
    )

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Настройка планировщика отчетов
    report_scheduler = ReportScheduler(application.bot, analytics_service)
    application.create_task(report_scheduler.schedule_reports())

    return application


async def main() -> None:
    """Основная функция запуска бота"""
    logger.info("Starting bot...")

    # Получаем настроенное приложение
    application = setup_application()

    # Проверка соединения с базой данных
    if 'db_session' in application.bot_data:
        logger.info("Database connection established")
    else:
        logger.error("Failed to establish database connection")
        return

    try:
        # Инициализация и запуск
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        logger.info("Bot started successfully!")

        # Настройка веб-сервера для webhook
        webhook_app = web.Application()

        # Получаем обработчик webhook из контекста приложения
        webhook_handler = application.bot_data["webhook_handler"]

        # Настраиваем маршруты webhook
        setup_webhook_routes(webhook_app, webhook_handler)

        # Запускаем веб-сервер на указанном порту
        webhook_port = WEBHOOK_PORT
        webhook_runner = web.AppRunner(webhook_app)
        await webhook_runner.setup()
        webhook_site = web.TCPSite(webhook_runner, WEBHOOK_LISTEN, webhook_port)
        await webhook_site.start()
        logger.info(f"Webhook server is running on {WEBHOOK_HOST}:{webhook_port}")

        # Создаем и устанавливаем событие для управления завершением
        stop_event = asyncio.Event()

        # Обработчик сигналов для корректного завершения
        def signal_handler():
            logger.info("Received stop signal, shutting down...")
            stop_event.set()

        # Регистрация обработчиков сигналов
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        # Ждем сигнала завершения
        await stop_event.wait()

        # Останавливаем веб-сервер
        await webhook_runner.cleanup()

    except Exception as e:
        logger.error(f"Error during bot execution: {e}")
    finally:
        # Очистка ресурсов
        if hasattr(application, 'updater') and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        await application.shutdown()

        # Закрываем соединение с базой данных
        if 'db_session' in application.bot_data:
            application.bot_data['db_session'].close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
