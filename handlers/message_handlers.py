# handlers/message_handlers.py
import logging
import asyncio
from io import BytesIO, StringIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from services.claude_service import ClaudeService
from config.settings import WELCOME_MESSAGE, HELP_MESSAGE
from config.knowledge_content import KNOWLEDGE_BASE
from services.analytics_service import AnalyticsService
from database.models import UserAction, UserPseudonym, DialogueMetadata, DialogueContent
from datetime import datetime

from services.subscription_service import SubscriptionService
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Настройка логирования
logger = logging.getLogger(__name__)


class NavigationMarkup:
    """Класс для создания элементов навигации"""

    @staticmethod
    def get_main_menu():
        """Создает основное меню с дополнительными кнопками для баланса и тарифов"""
        keyboard = [
            [KeyboardButton("🆕 Новая консультация")],
            [KeyboardButton("📚 База знаний"), KeyboardButton("💰 Баланс")],
            [KeyboardButton("💼 Тарифы"), KeyboardButton("💬 Оставить отзыв")],
            [KeyboardButton("❓ Помощь")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def get_knowledge_base_buttons(current_section=None):
        """Создает инлайн-кнопки для навигации по базе знаний"""
        sections = {
            'principles': "О принципах",
            'faq': "Частые вопросы"
        }

        # Убираем текущий раздел из списка
        if current_section and current_section in sections:
            sections.pop(current_section)

        # Создаем кнопки
        buttons = []
        items = list(sections.items())

        # Добавляем кнопки разделов парами
        for i in range(0, len(items), 2):
            row = []
            row.append(InlineKeyboardButton(items[i][1], callback_data=items[i][0]))
            if i + 1 < len(items):
                row.append(InlineKeyboardButton(items[i + 1][1], callback_data=items[i + 1][0]))
            buttons.append(row)

        # Добавляем кнопку возврата в главное меню
        buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])

        return InlineKeyboardMarkup(buttons)


async def log_user_action(context: ContextTypes.DEFAULT_TYPE, user_id: int, action_type: str, content: str = None):
    """Вспомогательная функция для логирования действий пользователя"""
    analytics = AnalyticsService(context.bot_data['db_session'])
    analytics.log_action(user_id, action_type, content)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/start')

    # Логируем первое использование
    analytics = AnalyticsService(context.bot_data['db_session'])
    analytics.log_first_time_user(user_id)

    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=NavigationMarkup.get_main_menu()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/help')

    await update.message.reply_text(
        HELP_MESSAGE,
        reply_markup=NavigationMarkup.get_main_menu()
    )


async def new_consultation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /new"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/new')

    # Создаем ClaudeService с текущей сессией
    claude_service = ClaudeService(context.bot_data['db_session'])
    claude_service.clear_conversation(user_id)

    await update.message.reply_text(
        "Готов к новой консультации. Расскажите о своей ситуации.",
        reply_markup=NavigationMarkup.get_main_menu()
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений с проверкой кредитов"""
    # Создаем ClaudeService с текущей сессией
    claude_service = ClaudeService(context.bot_data['db_session'])

    if not update.effective_user:
        logger.error("No user found in update")
        return

    user_id = update.effective_user.id
    message_text = update.message.text if update.message else None

    if not message_text:
        logger.error(f"No message text found for user {user_id}")
        return

    # Логируем входящее сообщение
    await log_user_action(context, user_id, 'message_received', message_text[:100])

    # Обработка команд через текстовые кнопки
    if message_text == "📚 База знаний":
        await log_user_action(context, user_id, 'menu_action', 'knowledge_base')
        await send_knowledge_base_menu(update, context)
        return

    if message_text == "🆕 Новая консультация":
        await log_user_action(context, user_id, 'menu_action', 'new_consultation')
        await new_consultation_command(update, context)
        return

    if message_text == "💬 Оставить отзыв":
        await log_user_action(context, user_id, 'menu_action', 'feedback')
        await handle_feedback(update, context)
        return

    if message_text == "❓ Помощь":
        await log_user_action(context, user_id, 'menu_action', 'help')
        await help_command(update, context)
        return

    if message_text == "💰 Баланс":
        await log_user_action(context, user_id, 'menu_action', 'balance')
        from handlers.payment_menu_handlers import handle_balance_command
        await handle_balance_command(update, context)
        return

    if message_text == "💼 Тарифы":
        await log_user_action(context, user_id, 'menu_action', 'pricing')
        from handlers.payment_menu_handlers import handle_pricing_command
        await handle_pricing_command(update, context)
        return

    # Проверяем наличие кредитов у пользователя
    # Получаем подписку и кредиты пользователя
    subscription_service = SubscriptionService(context.bot_data['db_session'])
    subscription_status = subscription_service.get_user_subscription_status(user_id)

    credits_remaining = subscription_status.get('credits_remaining', 0)

    # Если у пользователя нет кредитов, предлагаем пополнить баланс
    if credits_remaining <= 0:
        keyboard = [
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="show_tariffs")],
            [InlineKeyboardButton("🎁 Активировать пробный период", callback_data="activate_trial")]
        ]

        await update.message.reply_text(
            "⚠️ У вас закончились кредиты.\n\n"
            "Для продолжения консультаций необходимо пополнить баланс "
            "или активировать пробный период.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Обычная консультация
    try:
        # Логируем начало консультации
        await log_user_action(context, user_id, 'consultation_start', None)

        response = claude_service.get_consultation(user_id, message_text)

        # Списываем кредит за использование
        subscription_service.use_credit(user_id, 1)

        # Логируем успешное получение ответа
        await log_user_action(context, user_id, 'consultation_complete', str(len(response)))

        # Проверяем, сколько осталось кредитов после списания
        new_status = subscription_service.get_user_subscription_status(user_id)

        new_credits = new_status.get('credits_remaining', 0)

        # Добавляем информацию об оставшихся кредитах
        response_with_credits = (
            f"{response}\n\n"
            f"💰 Осталось кредитов: {new_credits}"
        )

        await update.message.reply_text(
            response_with_credits,
            reply_markup=NavigationMarkup.get_main_menu()
        )
    except Exception as e:
        # Логируем ошибку
        await log_user_action(context, user_id, 'error', str(e)[:100])
        logger.error(f"Error in message handler: {e}")
        if update.message:
            await update.message.reply_text(
                "Произошла ошибка при обработке сообщения. Пожалуйста, попробуйте позже.",
                reply_markup=NavigationMarkup.get_main_menu()
            )


# Остальные методы остаются без изменений
async def handle_knowledge_section(update: Update, context: ContextTypes.DEFAULT_TYPE, section: str):
    """Обработчик просмотра разделов базы знаний"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'knowledge_view', section)

    content = KNOWLEDGE_BASE.get(section)
    if not content:
        await log_user_action(context, user_id, 'error', f'section_not_found:{section}')
        return None
    return content


async def send_knowledge_base_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет меню базы знаний"""
    text = """База знаний по методу "обратного движения":

- Основные принципы метода /principles
- Частые вопросы /faq

Выберите интересующий раздел."""

    await update.message.reply_text(
        text,
        reply_markup=NavigationMarkup.get_knowledge_base_buttons()
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки"""
    query = update.callback_query
    await query.answer()

    # Обработка возврата в главное меню
    if query.data == "main_menu":
        await query.message.reply_text(
            f"{WELCOME_MESSAGE}\n\nВыберите действие:",
            reply_markup=NavigationMarkup.get_main_menu()
        )
        return

    section = KNOWLEDGE_BASE.get(query.data)
    if section:
        await query.message.reply_text(
            f"*{section['title']}*\n\n{section['content']}",
            parse_mode='Markdown',
            reply_markup=NavigationMarkup.get_knowledge_base_buttons(query.data)
        )
        return

async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команд для доступа к разделам базы знаний (/principles, /faq, /principle1, и т.д.)"""
    command = update.message.text[1:]  # Убираем '/' из команды

    section = KNOWLEDGE_BASE.get(command)
    if not section:
        await update.message.reply_text(
            "Извините, раздел не найден. Воспользуйтесь меню базы знаний.",
            reply_markup=NavigationMarkup.get_main_menu()
        )
        return

    await update.message.reply_text(
        f"*{section['title']}*\n\n{section['content']}",
        parse_mode='Markdown',
        reply_markup=NavigationMarkup.get_knowledge_base_buttons(command)
    )


async def principle_command(update: Update, context: ContextTypes.DEFAULT_TYPE, principle_number: str):
    """Обработчик команд для отдельных принципов"""
    principle_key = f'principle{principle_number}'
    principle = KNOWLEDGE_BASE.get(principle_key)

    if not principle:
        await update.message.reply_text(
            "Извините, информация о принципе временно недоступна.",
            reply_markup=NavigationMarkup.get_main_menu()
        )
        return

    await update.message.reply_text(
        f"*{principle['title']}*\n\n{principle['content']}",
        parse_mode='Markdown',
        reply_markup=NavigationMarkup.get_knowledge_base_buttons('principles')
    )


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды оставить отзыв"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/feedback')

    await update.message.reply_text(
        "Буду благодарен за ваш отзыв о консультации. Поделитесь, пожалуйста, своими впечатлениями или предложениями по улучшению сервиса.",
        reply_markup=NavigationMarkup.get_main_menu()
    )

    # Устанавливаем состояние ожидания отзыва
    context.user_data['awaiting_feedback'] = True


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /privacy"""
    # Импортируем напрямую, без относительного импорта
    from config.privacy_policy import PRIVACY_POLICY

    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/privacy')

    # Используем разбивку текста для обхода ограничений на длину сообщения
    policy_text = PRIVACY_POLICY
    max_length = 4000  # Максимальная длина сообщения в Telegram

    if len(policy_text) <= max_length:
        await update.message.reply_text(
            policy_text,
            parse_mode='Markdown'
        )
    else:
        # Разбиваем на части, если текст слишком длинный
        parts = [policy_text[i:i + max_length] for i in range(0, len(policy_text), max_length)]
        for part in parts:
            await update.message.reply_text(
                part,
                parse_mode='Markdown'
            )

    logger.info(f"Privacy policy sent to user {user_id}")


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /privacy"""
    logger.info("Privacy command handler called")

    # Импортируем напрямую, без относительного импорта
    from config.privacy_policy import PRIVACY_POLICY

    user_id = update.effective_user.id
    logger.info(f"Processing privacy command for user {user_id}")

    await log_user_action(context, user_id, 'command', '/privacy')

    try:
        # Сначала отправляем краткую версию политики прямо в чат
        brief_msg = (
            "*Политика конфиденциальности*\n\n"
            "Мы собираем только необходимую информацию для предоставления консультаций "
            "и улучшения работы бота.\n\n"
            "Вот краткое содержание нашей политики конфиденциальности:\n"
            "• Мы храним историю сообщений в течение 7 дней\n"
            "• Ваши данные защищены шифрованием\n"
            "• Вы имеете право запросить или удалить свои данные\n\n"
        )

        await update.message.reply_text(
            brief_msg + "Отправляю полную версию политики конфиденциальности...",
            parse_mode='Markdown'
        )

        # Создаем файл с полной политикой
        from io import BytesIO

        # Преобразуем Markdown разметку в обычный текст
        plain_policy = PRIVACY_POLICY.replace('*', '').replace('_', '')

        # Создаем байтовый поток для отправки
        policy_file = BytesIO(plain_policy.encode('utf-8'))
        policy_file.name = "privacy_policy.txt"

        # Отправляем документ
        await update.message.reply_document(
            document=policy_file,
            caption="Политика конфиденциальности бота-консультанта по методу 'обратного движения'"
        )

        logger.info(f"Privacy policy successfully sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error sending privacy policy: {e}")
        # В случае ошибки отправляем текстовое сообщение
        await update.message.reply_text(
            "Произошла ошибка при отправке политики конфиденциальности. "
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )


async def handle_data_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /mydata"""
    logger.info("Processing mydata command")

    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/mydata')

    await update.message.reply_text(
        "Подготовка экспорта ваших данных. Это может занять некоторое время."
    )

    try:
        # Получаем сессию БД
        session = context.bot_data['db_session']

        # Получаем pseudonym_id
        pseudonym = session.query(UserPseudonym).filter_by(user_id=user_id).first()
        pseudonym_id = pseudonym.pseudonym_id if pseudonym else str(user_id)

        # Получаем диалоги
        dialogue_metadata = session.query(DialogueMetadata).filter_by(pseudonym_id=pseudonym_id) \
            .order_by(DialogueMetadata.timestamp.desc()) \
            .limit(30).all()

        # Получаем историю действий
        user_actions = session.query(UserAction).filter(
            UserAction.user_id == user_id
        ).order_by(UserAction.created_at).all()

        # Формируем текстовый отчет
        buffer = StringIO()
        buffer.write("# Ваши данные в боте-консультанте\n\n")
        buffer.write(f"Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        buffer.write(f"Количество записей диалогов: {len(dialogue_metadata)}\n\n")

        # Включаем историю диалогов
        buffer.write("## История диалогов\n\n")
        for dialogue in dialogue_metadata:
            if dialogue.content:
                buffer.write(f"**{dialogue.role}** ({dialogue.timestamp.strftime('%Y-%m-%d %H:%M:%S')})\n")
                try:
                    # Здесь можно добавить расшифровку, если нужно
                    buffer.write(f"Длина сообщения: {len(dialogue.content.encrypted_content)} байт\n\n")
                except Exception as decrypt_error:
                    buffer.write(f"Ошибка при обработке содержимого: {decrypt_error}\n\n")

        # Добавляем информацию о действиях пользователя
        if user_actions:
            buffer.write("## История действий\n\n")
            for action in user_actions:
                buffer.write(f"**{action.action_type}** ({action.created_at.strftime('%Y-%m-%d %H:%M:%S')})\n")
                if action.content:
                    buffer.write(f"Содержание: {action.content[:500]}\n\n")

        # Создаем файл для отправки
        file_content = buffer.getvalue()
        file_bytes = BytesIO(file_content.encode('utf-8'))
        file_bytes.name = f"user_data_{user_id}.md"

        # Отправляем как документ
        await update.message.reply_document(
            document=file_bytes,
            caption="Вот экспорт ваших данных."
        )

        logger.info(f"Data export successfully sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error exporting user data: {e}", exc_info=True)
        await update.message.reply_text(
            "Произошла ошибка при экспорте данных. Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )


async def handle_data_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /deletedata"""
    logger.info("Processing deletedata command")

    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/deletedata')

    # Создаем клавиатуру для подтверждения с опциями полного удаления или анонимизации
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить все мои данные", callback_data="confirm_delete_data")],
        [InlineKeyboardButton("🔒 Анонимизировать мои данные", callback_data="anonymize_data")],
        [InlineKeyboardButton("❌ Нет, отменить", callback_data="cancel_delete_data")]
    ]

    await update.message.reply_text(
        "⚠️ Вы запросили управление вашими данными.\n\n"
        "*Варианты*:\n"
        "1. *Удалить данные* - все ваши сообщения будут полностью удалены из системы без возможности восстановления.\n\n"
        "2. *Анонимизировать* - ваш Telegram ID будет отвязан от ваших сообщений. Для вас это равносильно удалению "
        "(вы потеряете доступ к вашей истории), но данные останутся в системе в анонимной форме "
        "и могут использоваться для улучшения качества сервиса.\n\n"
        "Что вы хотите сделать?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_data_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback кнопок управления данными"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data

    try:
        # Получаем сервисы
        from services.data_retention_service import DataRetentionService
        from services.encryption_service import EncryptionService

        session = context.bot_data['db_session']
        encryption_service = EncryptionService(session)
        retention_service = DataRetentionService(session, encryption_service)

        if action == "confirm_delete_data":
            logger.info(f"Confirming data deletion for user {user_id}")

            # Удаляем данные, используя correct метод manual_user_data_cleanup
            result = retention_service.manual_user_data_cleanup(
                user_id,
                reason="User request via /deletedata command"
            )

            # Проверяем, получен ли словарь или число
            if isinstance(result, dict):
                # Если результат — словарь, форматируем его для вывода
                deleted_actions = result.get('deleted_actions', 0)
                deleted_messages = result.get('deleted_messages', 0)
                deleted_feedbacks = result.get('deleted_feedbacks', 0)
                deleted_subscriptions = result.get('deleted_subscriptions', 0)

                total_deleted = deleted_actions + deleted_messages + deleted_feedbacks + deleted_subscriptions

                message = (
                    f"✅ Ваши персональные данные успешно удалены.\n\n"
                    f"Удалено записей: {total_deleted}\n"
                    f"• Сообщения: {deleted_messages}\n"
                    f"• Действия: {deleted_actions}\n"
                    f"• Отзывы: {deleted_feedbacks}\n\n"
                    f"Информация о вашей подписке сохранена для обслуживания вашего аккаунта.\n"
                    f"Вы можете продолжать использовать бота."
                )
            else:
                # Если результат — число, показываем общее количество
                message = (
                    f"✅ Ваши данные успешно удалены.\n\n"
                    f"Удалено записей: {result}\n\n"
                    f"Вы можете продолжать использовать бота."
                )

            await query.message.edit_text(message)
            logger.info(f"Successfully deleted data for user {user_id}")

        elif action == "anonymize_data":
            logger.info(f"Anonymizing data for user {user_id}")

            # Анонимизируем пользователя
            success = retention_service.anonymize_user(
                user_id,
                reason="User request via /deletedata command"
            )

            if success:
                await query.message.edit_text(
                    "✅ Ваши данные успешно анонимизированы.\n\n"
                    "Ваш Telegram ID больше не связан с историей сообщений. Для вас это означает:\n\n"
                    "• Вы теряете доступ к предыдущей истории сообщений\n"
                    "• При следующем обращении вы начнете общение как новый пользователь\n"
                    "• Ваши анонимизированные сообщения останутся в системе для улучшения сервиса\n\n"
                    "Ваша приватность соблюдена: никто не сможет связать эти сообщения с вами."
                )
                logger.info(f"Successfully anonymized user {user_id}")
            else:
                await query.message.edit_text(
                    "❌ Произошла ошибка при анонимизации данных.\n"
                    "Пожалуйста, попробуйте позже или обратитесь в поддержку."
                )
                logger.error(f"Failed to anonymize user {user_id}")

        elif action == "cancel_delete_data":
            logger.info(f"Data management cancelled by user {user_id}")
            await query.message.edit_text(
                "Операция управления данными отменена. Ваши данные остаются без изменений."
            )

    except Exception as e:
        logger.error(f"Error in data management: {e}")
        await query.message.edit_text(
            "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )
