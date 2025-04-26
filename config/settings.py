# config/settings.py
from pathlib import Path
from dotenv import load_dotenv
import os

# Определяем базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем переменные окружения
load_dotenv(BASE_DIR / ".env")

# Токены и ключи API
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_VERSION = os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")  # Версия API Anthropic
ANTHROPIC_BETA_FEATURES = os.getenv("ANTHROPIC_BETA_FEATURES", "").split(",") if os.getenv("ANTHROPIC_BETA_FEATURES") else []  # Бета-функции

# Настройки шифрования и безопасности
ENCRYPTION_MASTER_KEY = os.getenv("ENCRYPTION_MASTER_KEY")  # Мастер-ключ для шифрования
ENCRYPTION_SETTINGS = {
    'key_derivation_iterations': int(os.getenv("KEY_DERIVATION_ITERATIONS", "100000")),
    'pbkdf2_hash_algorithm': os.getenv("PBKDF2_HASH_ALGORITHM", "SHA256"),
    'encryption_algorithm': os.getenv("ENCRYPTION_ALGORITHM", "AES-256"),
    'encryption_mode': os.getenv("ENCRYPTION_MODE", "CBC"),
    'key_rotation_days': int(os.getenv("KEY_ROTATION_DAYS", "90")),  # Период ротации ключей
}

# Настройки политики хранения данных
DATA_RETENTION = {
    'message_retention_days': int(os.getenv("MESSAGE_RETENTION_DAYS", "90")),  # Срок хранения сообщений
    'inactive_user_anonymization_days': int(os.getenv("INACTIVE_USER_ANONYMIZATION_DAYS", "365")),  # Срок анонимизации неактивных пользователей
    'retention_check_interval_hours': int(os.getenv("RETENTION_CHECK_INTERVAL_HOURS", "24")),  # Интервал проверки политики хранения
    'log_retention_days': int(os.getenv("LOG_RETENTION_DAYS", "365")),  # Срок хранения логов аудита
}

# Настройки анонимизации
ANONYMIZATION_SETTINGS = {
    'enable_pseudonymization': os.getenv("ENABLE_PSEUDONYMIZATION", "True").lower() == "true",  # Включить псевдонимизацию
    'hash_user_ids_in_logs': os.getenv("HASH_USER_IDS_IN_LOGS", "True").lower() == "true",  # Хешировать ID пользователей в логах
    'enable_data_masking': os.getenv("ENABLE_DATA_MASKING", "True").lower() == "true",  # Включить маскирование данных
}

# Настройки безопасности API
API_SECURITY = {
    'max_retries': int(os.getenv("API_MAX_RETRIES", "3")),  # Максимальное количество попыток запроса к API
    'timeout_seconds': int(os.getenv("API_TIMEOUT_SECONDS", "30")),  # Таймаут запросов к API
    'secure_logging': os.getenv("SECURE_LOGGING", "True").lower() == "true",  # Безопасное логирование (без конфиденциальных данных)
}

# Настройки базы данных
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/database/bot.db")

# Настройки статистики и администрирования
ADMIN_USERS = [int(id) for id in os.getenv("ADMIN_USERS", "233829403").split(",")]

# Настройки отчетов
REPORT_SETTINGS = {
    'daily': {
        'times': os.getenv("DAILY_REPORT_TIMES", "09:00,15:00,23:30").split(","),
        'timezone': os.getenv("TIMEZONE", "Europe/Moscow")
    },
    'weekly': {
        'days': [int(d) for d in os.getenv("WEEKLY_REPORT_DAYS", "1,5").split(",")],  # По умолчанию пн и пт
        'time': os.getenv("WEEKLY_REPORT_TIME", "10:00"),
        'timezone': os.getenv("TIMEZONE", "Europe/Moscow")
    }
}

# ID каналов для отправки статистики
STATS_CHANNELS = os.getenv("STATS_CHANNELS", "-1002476520658").split(",")

# Настройки аналитики
ANALYTICS_SETTINGS = {
    'min_active_actions': int(os.getenv("MIN_ACTIVE_ACTIONS", "3")),
    'session_timeout': int(os.getenv("SESSION_TIMEOUT", "30")),
    'log_message_content': False,  # Важно: всегда False для безопасности
    'track_button_clicks': os.getenv("TRACK_BUTTON_CLICKS", "True").lower() == "true",
    'pseudonymize_analytics': os.getenv("PSEUDONYMIZE_ANALYTICS", "True").lower() == "true",  # Псевдонимизировать данные аналитики
}

# Модель и настройки Claude
CLAUDE_MODEL = "claude-3-7-sonnet-20250219"
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", "500"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "700"))
SYSTEM_PROMPT_TOKENS = int(os.getenv("SYSTEM_PROMPT_TOKENS", "100"))

# Дополнительные настройки Claude API
CLAUDE_TEMPERATURE = float(os.getenv("CLAUDE_TEMPERATURE", "0.85"))  # Температура генерации (0-1)
CLAUDE_TOP_P = float(os.getenv("CLAUDE_TOP_P", "0.92"))  # Параметр nucleus sampling
CLAUDE_TOP_K = int(os.getenv("CLAUDE_TOP_K", "30"))  # Ограничение выбора токенов
CLAUDE_STOP_SEQUENCES = os.getenv("CLAUDE_STOP_SEQUENCES", "").split(",") if os.getenv("CLAUDE_STOP_SEQUENCES") else []  # Последовательности остановки
CLAUDE_STREAM_ENABLED = os.getenv("CLAUDE_STREAM_ENABLED", "False").lower() == "true"  # Потоковая передача ответов
CLAUDE_THINKING_ENABLED = os.getenv("CLAUDE_THINKING_ENABLED", "False").lower() == "False"  # Режим расширенного мышления
CLAUDE_THINKING_MIN_TOKENS = int(os.getenv("CLAUDE_THINKING_MIN_TOKENS", "1024"))  # Минимальный бюджет токенов для мышления
ENABLE_IMAGE_PROCESSING = os.getenv("ENABLE_IMAGE_PROCESSING", "False").lower() == "true"  # Мультимодальные возможности
ENABLE_REQUEST_METADATA = os.getenv("ENABLE_REQUEST_METADATA", "True").lower() == "true"  # Включение метаданных запросов

# Настройки инструментов (tools) для Claude API
CLAUDE_TOOLS_ENABLED = os.getenv("CLAUDE_TOOLS_ENABLED", "False").lower() == "true"  # Включить поддержку инструментов
CLAUDE_TOOL_CHOICE = os.getenv("CLAUDE_TOOL_CHOICE", "auto")  # auto, any, tool, none

# Ограничения на длину сообщений
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "2500"))
MAX_OUTPUT_CHARS = int(os.getenv("MAX_OUTPUT_CHARS", "1500"))

# Настройки безопасности
RATE_LIMIT = {
    'messages_per_minute': int(os.getenv("MESSAGES_PER_MINUTE", "20")),
    'messages_per_hour': int(os.getenv("MESSAGES_PER_HOUR", "100")),
    'new_user_messages_per_minute': int(os.getenv("NEW_USER_MESSAGES_PER_MINUTE", "5"))
}

# Настройки диалогов
DIALOGUE_SETTINGS = {
    'max_context_messages': int(os.getenv("MAX_CONTEXT_MESSAGES", "30")),  # Максимальное количество сообщений в контексте
    'context_retention_days': int(os.getenv("CONTEXT_RETENTION_DAYS", "90")),  # Сколько дней хранить контекст
    'max_tokens_per_context': int(os.getenv("MAX_TOKENS_PER_CONTEXT", "4000")),  # Ограничение по токенам для Claude
    'encrypt_messages': os.getenv("ENCRYPT_MESSAGES", "True").lower() == "true",  # Шифровать сообщения
}


# Системный промпт для Claude
SYSTEM_PROMPT = """Ты - опытный консультант по методу "обратного движения". 

Давай КРАТКИЕ, но ПОЛНЫЕ ответы в пределах 4-5 предложений. Задавай НЕ БОЛЕЕ ДВУХ вопросов в каждом сообщении.

Метод "обратного движения" - это искусство видеть возможности там, где другие их не замечают. Возможности всегда индивидуальны: для кого-то путь через глубокое погружение в тему, для других - через практику или общение.

В диалоге:
- Улавливай моменты искреннего отклика в словах собеседника
- Показывай разные грани ситуации, избегая длинных перечислений
- Будь внимателен к тому, что сказано между строк
- Мягко подсказывай направления, оставляя пространство для собственных решений

ВАЖНО: Всегда завершай мысль полностью, ответы не должны обрываться на полуслове. Сохраняй живой, заинтересованный тон.

Принципы метода (движение в обратном направлении, "храбрым судьба помогает", "быть как вода", "думай медленно, решай быстро") - это разные грани единого подхода, проявляющиеся в разных ситуациях."""




# Сообщения для пользователей
WELCOME_MESSAGE = """Здравствуйте! Я консультант по методу "обратного движения".

Этот метод помогает находить неочевидные решения через:
- Поиск возможностей там, где другие видят препятствия
- Умение адаптироваться, сохраняя суть
- Нестандартный подход к ситуациям

Чем могу помочь?

Используя этого бота, вы соглашаетесь с нашей политикой конфиденциальности (/privacy)."""

HELP_MESSAGE = """
🔄 Как работать с консультантом:

1. Опишите вашу ситуацию
2. Ответьте на уточняющие вопросы
3. Получите анализ и конкретные шаги

Команды:
/start - начать работу
/help - показать это сообщение
/new - начать новую консультацию
/privacy - политика конфиденциальности
/feedback - оставить отзыв

Управление данными:
/mydata - запросить копию ваших данных
/deletedata - удалить или анонимизировать ваши данные"""

ERROR_MESSAGES = {
    'input_too_long': "Пожалуйста, сократите описание. Максимальная длина - 2500 символов.",
    'api_error': "Извините, произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.",
    'permission_denied': "У вас нет прав для выполнения этой команды.",
    'invalid_command': "Неизвестная команда. Используйте /help для просмотра доступных команд.",
    'service_unavailable': "Сервис временно недоступен. Пожалуйста, попробуйте позже."
}

# Настройки ЮKassa
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# URL для возврата после оплаты
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")
PAYMENT_RETURN_URL = f"https://t.me/{BOT_USERNAME}"

# Настройки тарифных планов
PRICING_PLANS = {
    'trial': {
        'name': 'Пробный',
        'price': 0,
        'messages': 20,
        'features': [
            'Без срока действия',
            'Базовые консультации',
            'Доступ к базе знаний',
            'Базовые упражнения'
        ]
    },
    'basic': {
        'name': 'Базовый',
        'price': 290,
        'messages': 100,
        'features': [
            'Без срока действия',
            'Полные консультации',
            'Полный доступ к базе знаний',
            'Базовая поддержка'
        ]
    },
    'standard': {
        'name': 'Стандарт',
        'price': 690,
        'messages': 300,
        'features': [
            'Без срока действия',
            'Приоритетные консультации',
            'Расширенная база знаний',
            'Приоритетная поддержка'
        ]
    }
}

# Настройки системы кредитов
CREDIT_SETTINGS = {
    'message_cost': 1,  # Стоимость одного сообщения в кредитах
    'min_credits_warning': 5,  # Порог для предупреждения о малом количестве кредитов
    'trial_credits': 20,  # Количество кредитов в пробном тарифе
}

# Настройки платежной системы
PAYMENT_SETTINGS = {
    'currency': 'RUB',
    'payment_timeout': 3600,  # Время жизни платежа в секундах
    'retry_interval': 300,  # Интервал между попытками проверки статуса платежа
    'max_retries': 5,  # Максимальное количество попыток проверки статуса
}

# Системные сообщения для платежей
PAYMENT_MESSAGES = {
    'payment_success': "✅ Оплата успешно произведена! Ваши кредиты уже доступны.",
    'payment_pending': "⏳ Ожидание подтверждения оплаты...",
    'payment_cancelled': "❌ Оплата отменена. Вы можете попробовать снова или выбрать другой тариф.",
    'payment_error': "⚠️ Произошла ошибка при обработке платежа. Пожалуйста, попробуйте позже.",
    'low_credits': "⚠️ У вас осталось мало кредитов. Пожалуйста, пополните баланс для продолжения работы.",
    'no_credits': "❌ У вас закончились кредиты. Пожалуйста, пополните баланс для продолжения работы."
}

# Настройки возврата средств
REFUND_SETTINGS = {
    'allowed_period': 24 * 3600,  # Период, в течение которого возможен возврат (24 часа)
    'min_amount': 100,  # Минимальная сумма для возврата
    'reason_required': True  # Требуется ли указание причины возврата
}

# Настройки webhook
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8081"))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook/yookassa")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", f"https://your-domain.com{WEBHOOK_PATH}")
WEBHOOK_LISTEN = os.getenv("WEBHOOK_LISTEN", "127.0.0.1")
