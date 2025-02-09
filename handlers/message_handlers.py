# handlers/message_handlers.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from services.claude_service import ClaudeService
from config.settings import WELCOME_MESSAGE, HELP_MESSAGE
from config.knowledge_content import KNOWLEDGE_BASE, PRACTICE_EXERCISES
from services.analytics_service import AnalyticsService
from database.models import ExerciseFeedback
from datetime import datetime

# Создаем единый экземпляр сервиса
claude_service = ClaudeService()

# Настройка логирования
logger = logging.getLogger(__name__)

class NavigationMarkup:
    """Класс для создания элементов навигации"""

    @staticmethod
    def get_main_menu():
        """Создает основное меню с критичными действиями"""
        keyboard = [
            [KeyboardButton("🆕 Новая консультация")],
            [KeyboardButton("📚 База знаний"), KeyboardButton("❓ Помощь")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def get_knowledge_base_buttons(current_section=None):
        """Создает инлайн-кнопки для навигации по базе знаний"""
        sections = {
            'principles': "О принципах",
            'examples': "Примеры",
            'faq': "Частые вопросы",
            'practice': "Практика"
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

    @staticmethod
    def get_exercise_buttons():
        """Создает кнопки для выбора практического упражнения"""
        keyboard = [
            [InlineKeyboardButton("1️⃣ Анализ прошлого опыта", callback_data="exercise_1")],
            [InlineKeyboardButton("2️⃣ Поиск возможностей", callback_data="exercise_2")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_exercise_keyboard():
        """Создает клавиатуру для упражнения"""
        keyboard = [
            [InlineKeyboardButton("✅ Завершить упражнение", callback_data="complete_exercise")],
            [InlineKeyboardButton("📚 О принципах", callback_data="principles"),
             InlineKeyboardButton("📝 Примеры", callback_data="examples")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)


async def log_user_action(context: ContextTypes.DEFAULT_TYPE, user_id: int, action_type: str, content: str = None):
    """Вспомогательная функция для логирования действий пользователя"""
    analytics = AnalyticsService(context.bot_data['db_session'])
    await analytics.log_action(user_id, action_type, content)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/start')

    # Логируем первое использование
    analytics = AnalyticsService(context.bot_data['db_session'])
    await analytics.log_first_time_user(user_id)

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

    claude_service.clear_conversation(user_id)
    await update.message.reply_text(
        "Готов к новой консультации. Расскажите о своей ситуации.",
        reply_markup=NavigationMarkup.get_main_menu()
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    if not update.effective_user:
        logger.error("No user found in update")
        return

    user_id = update.effective_user.id
    message_text = update.message.text if update.message else None

    if not message_text:
        logger.error(f"No message text found for user {user_id}")
        return

    # Проверяем ожидание фидбека
    if context.user_data.get('awaiting_feedback'):
        exercise_data = context.user_data['awaiting_feedback']

        # Сохраняем фидбек в БД
        try:
            feedback = ExerciseFeedback(
                user_id=user_id,
                exercise_id=exercise_data['exercise_id'],
                exercise_date=datetime.utcnow(),
                feedback_text=message_text,
                context=exercise_data['context']
            )

            session = context.bot_data['db_session']
            session.add(feedback)
            session.commit()

            await update.message.reply_text(
                "Спасибо за ваш отзыв! Он поможет сделать упражнения еще лучше.",
                reply_markup=NavigationMarkup.get_main_menu()
            )

            # Очищаем состояние
            context.user_data.clear()
            return

        except Exception as e:
            logger.error(f"Error saving feedback: {e}")
            await update.message.reply_text(
                "Извините, произошла ошибка при сохранении отзыва.",
                reply_markup=NavigationMarkup.get_main_menu()
            )
            context.user_data.clear()
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

    if message_text == "❓ Помощь":
        await log_user_action(context, user_id, 'menu_action', 'help')
        await help_command(update, context)
        return

    # Проверяем, находится ли пользователь в процессе выполнения упражнения
    current_exercise = context.user_data.get('current_exercise')
    exercise_stage = context.user_data.get('exercise_stage')

    if current_exercise and exercise_stage:
        await log_user_action(context, user_id, 'exercise_input', f"{current_exercise}:{exercise_stage}")
        await handle_exercise_input(update, context, current_exercise, exercise_stage, message_text)
        return

    # Обычная консультация
    try:
        # Логируем начало консультации
        await log_user_action(context, user_id, 'consultation_start', None)

        response = claude_service.get_consultation(user_id, message_text)

        # Логируем успешное получение ответа
        await log_user_action(context, user_id, 'consultation_complete', str(len(response)))

        await update.message.reply_text(
            response,
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


async def handle_knowledge_section(update: Update, context: ContextTypes.DEFAULT_TYPE, section: str):
    """Обработчик просмотра разделов базы знаний"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'knowledge_view', section)

    content = KNOWLEDGE_BASE.get(section)
    if not content:
        await log_user_action(context, user_id, 'error', f'section_not_found:{section}')
        return None
    return content


async def handle_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE, exercise_number: str):
    """Обработчик выбора упражнения"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'exercise_start', f'exercise_{exercise_number}')

    exercise = PRACTICE_EXERCISES.get(f'exercise_{exercise_number}')
    if not exercise:
        await log_user_action(context, user_id, 'error', f'exercise_not_found:{exercise_number}')

        # Определяем, откуда пришел запрос
        message = update.message or update.callback_query.message
        await message.reply_text(
            "Извините, такое упражнение не найдено.",
            reply_markup=NavigationMarkup.get_main_menu()
        )
        return

    message = f"*{exercise['title']}*\n\n"
    message += exercise.get('description', "\n".join(exercise['steps']))

    # Сохраняем состояние упражнения
    context.user_data['current_exercise'] = f'exercise_{exercise_number}'
    context.user_data['exercise_stage'] = 'waiting_for_description'

    # Определяем, откуда пришел запрос
    response_message = update.message or update.callback_query.message
    await response_message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=NavigationMarkup.get_exercise_keyboard()
    )


async def handle_exercise_input(update: Update, context: ContextTypes.DEFAULT_TYPE,
                              current_exercise: str, exercise_stage: str, message_text: str):
    """Обработчик ввода пользователя в процессе выполнения упражнения"""
    user_id = update.effective_user.id
    exercise = PRACTICE_EXERCISES.get(current_exercise)

    if not exercise:
        await update.message.reply_text(
            "Извините, произошла ошибка. Давайте начнем упражнение заново.",
            reply_markup=NavigationMarkup.get_main_menu()
        )
        context.user_data.clear()
        return

    if exercise_stage == 'waiting_for_description':
        context.user_data['situation_description'] = message_text

        # Упрощенный промпт без лишних инструкций
        prompt = f"Помогите применить метод обратного движения к ситуации: {message_text}"

        try:
            response = await claude_service.get_consultation(user_id, prompt)
            await update.message.reply_text(
                response,
                reply_markup=NavigationMarkup.get_exercise_keyboard()
            )
            return
        except Exception as e:
            logger.error(f"Error in exercise AI response: {e}")
            await update.message.reply_text(
                "Извините, произошла ошибка. Попробуем начать сначала?",
                reply_markup=NavigationMarkup.get_main_menu()
            )
            context.user_data.clear()
            return


async def send_knowledge_base_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет меню базы знаний"""
    text = """База знаний по методу "обратного движения":

- Основные принципы метода /principles
- Примеры применения /examples
- Частые вопросы /faq
- Практические упражнения /practice

Выберите интересующий раздел."""

    await update.message.reply_text(
        text,
        reply_markup=NavigationMarkup.get_knowledge_base_buttons()
    )


async def handle_exercise_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик завершения упражнения"""
    query = update.callback_query
    user_id = query.from_user.id

    # Получаем данные упражнения из context.user_data
    exercise_data = {
        'exercise_id': context.user_data.get('current_exercise'),
        'context': context.user_data.get('situation_description', '')
    }

    # Запрашиваем обратную связь
    await query.message.reply_text(
        "Спасибо за выполнение упражнения! Поделитесь, пожалуйста, своими впечатлениями:\n"
        "- Было ли упражнение полезным?\n"
        "- Что показалось наиболее ценным?\n"
        "- Что можно улучшить?",
        reply_markup=NavigationMarkup.get_main_menu()
    )

    # Сохраняем состояние ожидания фидбека
    context.user_data['awaiting_feedback'] = exercise_data

    # Сохраняем состояние ожидания фидбека
    context.user_data['awaiting_feedback'] = exercise_data

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

    # Обработка выбора упражнения
    if query.data.startswith('exercise_'):
        exercise_number = query.data.split('_')[1]
        await handle_exercise(update, context, exercise_number)
        return

    if query.data == "complete_exercise":
        await handle_exercise_completion(update, context)
        return

    if query.data == "main_menu":
        await query.message.reply_text(
            f"{WELCOME_MESSAGE}\n\nВыберите действие:",
            reply_markup=NavigationMarkup.get_main_menu()
        )
        return

    section = KNOWLEDGE_BASE.get(query.data)
    if section:
        if query.data == 'practice':
            await query.message.reply_text(
                f"*{section['title']}*\n\n{section['content']}",
                parse_mode='Markdown',
                reply_markup=NavigationMarkup.get_exercise_buttons()
            )
        else:
            await query.message.reply_text(
                f"*{section['title']}*\n\n{section['content']}",
                parse_mode='Markdown',
                reply_markup=NavigationMarkup.get_knowledge_base_buttons(query.data)
            )
        return

async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команд для доступа к разделам базы знаний (/principles, /examples, и т.д.)"""
    command = update.message.text[1:]  # Убираем '/' из команды

    # Обрабатываем команды упражнений отдельно
    if command.startswith('exercise'):
        try:
            exercise_number = command.replace('exercise', '')
            await handle_exercise(update, context, exercise_number)
            return
        except ValueError:
            pass

    section = KNOWLEDGE_BASE.get(command)
    if not section:
        await update.message.reply_text(
            "Извините, раздел не найден. Воспользуйтесь меню базы знаний.",
            reply_markup=NavigationMarkup.get_main_menu()
        )
        return

    if command == 'practice':
        # Для раздела практики показываем меню выбора упражнения
        await update.message.reply_text(
            f"*{section['title']}*\n\n{section['content']}",
            parse_mode='Markdown',
            reply_markup=NavigationMarkup.get_exercise_buttons()
        )
    else:
        # Для остальных разделов показываем контент и навигацию
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


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /support"""
    user_id = update.effective_user.id
    await log_user_action(context, user_id, 'command', '/support')

    support_message = """🌱 → 🌿 → 🌳 *Развитие проекта*

Рад, что вы интересуетесь развитием Метода обратного движения!

*Над чем ведется работа:*
• Написание книги о Методе и его применении
• Исследование и документирование новых кейсов проявления Метода
• Развитие сообщества практиков Метода
• Улучшение бота-консультанта и базы знаний

*Как поддержать проект:*
Если хотите помочь в развитии, можно сделать перевод любой суммы по следюущим реквизитам:
• TON: `UQBgmqEz2BjkjfbaTq2HLYBwltRiI6F1xCVU521qpB3JEyu0`
• USDT (TRC20): `TKWcNCibyZ3vGsTTXVaWgs5N9KmQkKmD5n`

*На что идут и в будущем будут идти средства:*
• Исследование и развитие Метода
• Написание и публикация книги
• Развитие онлайн-инструментов
• Организация практических семинаров
• Расширение команды проекта

Спасибо, что помогаете делать проект лучше! ⭐️"""

    await update.message.reply_text(
        support_message,
        parse_mode='Markdown',
        reply_markup=NavigationMarkup.get_main_menu()
    )
