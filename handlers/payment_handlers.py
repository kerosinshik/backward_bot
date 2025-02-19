# handlers/payment_handlers.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from backward_bot.config.settings import PRICING_PLANS
from backward_bot.services.payment_service import PaymentService
from backward_bot.services.subscription_service import SubscriptionService
from backward_bot.keyboards.payment_keyboard import PaymentKeyboards
from backward_bot.database.models import UserCredits

logger = logging.getLogger(__name__)


class PaymentHandlers:
    """Класс для обработки платежных команд"""

    def __init__(self, payment_service: PaymentService):
        """
        Инициализация обработчика платежей

        Args:
            payment_service: Сервис для работы с платежами
        """
        self.payment_service = payment_service

    async def show_pricing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню с тарифными планами"""
        keyboard = PaymentKeyboards.get_tariff_selection_keyboard()

        await update.message.reply_text(
            "Выберите тарифный план:\n\n"
            "🎁 *Пробный*\n"
            "• 20 сообщений\n"
            "• Без срока действия\n"
            "• Базовые консультации\n\n"
            "💫 *Базовый*\n"
            "• 100 сообщений\n"
            "• Без срока действия\n"
            "• Полные консультации\n"
            "• Базовая поддержка\n\n"
            "⭐️ *Стандарт*\n"
            "• 300 сообщений\n"
            "• Без срока действия\n"
            "• Приоритетные консультации\n"
            "• Приоритетная поддержка",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def show_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает текущий баланс кредитов"""
        user_id = update.effective_user.id
        credits = await self.payment_service.get_user_credits(user_id)

        message = (
            f"💰 *Ваш баланс*\n\n"
            f"Доступно сообщений: {credits if credits is not None else 0}\n\n"
        )

        keyboard = PaymentKeyboards.get_credits_info_keyboard()

        await update.message.reply_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def handle_payment_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback-запросов для платежей"""
        try:
            query = update.callback_query
            logger.info(f"FULL CALLBACK DATA: {update}")
            logger.info(f"Received callback query with data: {query.data}")
            logger.info(f"User data: {context.user_data}")
            logger.info(f"Bot data: {context.bot_data.keys()}")

            await query.answer()

            data = query.data.split(':')
            action = data[0]

            logger.info(f"Processing action: {action}")

            if action == "select_plan":
                plan_id = data[1]
                plan = PRICING_PLANS.get(plan_id)

                logger.info(f"Selected plan: {plan_id}, Plan details: {plan}")

                if not plan:
                    logger.error(f"Plan not found: {plan_id}")
                    await query.message.edit_text("Ошибка: тариф не найден")
                    return

                if plan_id == 'trial':
                    logger.info("Processing trial activation")
                    await self._handle_trial_activation(query, context)
                else:
                    logger.info("Processing demo payment")
                    keyboard = [
                        [InlineKeyboardButton("✅ Подтвердить оплату (демо)", callback_data="demo_payment_success")],
                        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment")]
                    ]

                    message_text = (
                        f"🔄 *Демонстрационный режим оплаты*\n\n"
                        f"Тариф: {plan['name']}\n"
                        f"Сообщений: {plan['messages']}\n"
                        f"Стоимость: {plan['price']}₽\n\n"
                        f"Это демо-версия процесса оплаты.\n"
                        f"В реальной версии здесь будет переход на страницу ЮKassa.\n\n"
                        f"Нажмите 'Подтвердить', чтобы эмулировать успешную оплату."
                    )

                    context.user_data['selected_plan'] = plan_id

                    await query.message.edit_text(
                        message_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )

            elif action == "demo_payment_success":
                logger.info("STARTING DEMO PAYMENT SUCCESS HANDLER")
                # Проверяем, что план выбран
                if 'selected_plan' not in context.user_data:
                    logger.error("No selected plan in user data")
                    await query.message.edit_text(
                        "❌ Произошла ошибка: План не выбран. Пожалуйста, начните процесс заново.",
                        reply_markup=PaymentKeyboards.get_tariff_selection_keyboard()
                    )
                    return

                # Вызываем метод обработки демо-платежа
                await self._handle_demo_payment_success(query, context)

            elif action == "cancel_payment":
                await self._handle_payment_cancellation(query)

        except Exception as e:
            logger.error(f"CRITICAL ERROR in payment callback: {e}", exc_info=True)
            await query.message.edit_text(
                f"Произошла критическая ошибка: {str(e)}"
            )

    async def _handle_demo_payment(self, query: Update.callback_query, context, plan: dict):
        """Обработчик демо-платежа"""
        # Находим ключ плана в PRICING_PLANS
        plan_id = next(key for key, value in PRICING_PLANS.items() if value == plan)

        # Сохраняем план в user_data
        context.user_data['selected_plan'] = plan_id

        logger.info(f"Handling demo payment for plan: {plan['name']}")

        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить оплату (демо)", callback_data="demo_payment_success")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment")]
        ]

        message_text = (
            f"🔄 *Демонстрационный режим оплаты*\n\n"
            f"Тариф: {plan['name']}\n"
            f"Сообщений: {plan['messages']}\n"
            f"Стоимость: {plan['price']}₽\n\n"
            f"Это демо-версия процесса оплаты.\n"
            f"В реальной версии здесь будет переход на страницу ЮKassa.\n\n"
            f"Нажмите 'Подтвердить', чтобы эмулировать успешную оплату."
        )

        await query.message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def _handle_demo_payment_success(self, query: Update.callback_query, context):
        """Обработчик успешной демо-оплаты"""
        try:
            logger.info("ENTERED _handle_demo_payment_success")

            user_id = query.from_user.id
            logger.info(f"User ID: {user_id}")

            # Получаем выбранный план, по умолчанию - стандартный
            plan_id = context.user_data.get('selected_plan', 'standard')
            logger.info(f"Plan ID from user_data: {plan_id}")

            plan = PRICING_PLANS.get(plan_id)
            logger.info(f"Selected Plan details: {plan}")

            if not plan:
                logger.error(f"Invalid plan selected: {plan_id}")
                await query.message.edit_text(
                    "❌ Произошла ошибка: Некорректный тариф.\n"
                    "Пожалуйста, выберите тариф заново.",
                    reply_markup=PaymentKeyboards.get_tariff_selection_keyboard()
                )
                return

            # НОВОЕ: Явная проверка наличия сессии
            if 'db_session' not in context.bot_data:
                logger.error("NO DATABASE SESSION IN BOT DATA")
                await query.message.edit_text("Системная ошибка: отсутствует подключение к базе данных")
                return

            # Создаем сессию базы данных
            session = context.bot_data['db_session']

            # Активируем демо-план
            user_credits = session.query(UserCredits).filter_by(user_id=user_id).first()

            if not user_credits:
                user_credits = UserCredits(user_id=user_id, credits_remaining=0)
                session.add(user_credits)

            # Добавляем кредиты
            user_credits.credits_remaining += plan['messages']
            session.commit()

            logger.info(f"Successfully added {plan['messages']} credits for user {user_id}")

            await query.message.edit_text(
                "✅ *Оплата успешно завершена!*\n\n"
                f"Тариф: *{plan['name']}*\n"
                f"Доступно сообщений: *{plan['messages']}*\n"
                f"Баланс кредитов: *{user_credits.credits_remaining}*\n\n"
                "Вы можете начать использовать бота.\n\n"
                "_Это демонстрационный режим_",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Начать использовать", callback_data="start_using")],
                    [InlineKeyboardButton("📊 Проверить баланс", callback_data="check_balance")]
                ])
            )

        except Exception as e:
            logger.error(f"CRITICAL DEMO PAYMENT ERROR: {e}", exc_info=True)
            await query.message.edit_text(
                f"❌ Произошла критическая ошибка: {str(e)}\n"
                "Пожалуйста, обратитесь в поддержку.",
                reply_markup=PaymentKeyboards.get_tariff_selection_keyboard()
            )

    async def _handle_trial_activation(self, query: Update.callback_query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка активации пробного периода"""
        user_id = query.from_user.id

        try:
            # Проверяем, не был ли уже использован пробный период
            session = context.bot_data['db_session']
            user_credits = session.query(UserCredits).filter_by(user_id=user_id).first()

            if user_credits and user_credits.has_used_trial:
                keyboard = [
                    [InlineKeyboardButton("💫 Базовый (290₽)", callback_data="select_plan:basic")],
                    [InlineKeyboardButton("⭐️ Стандарт (690₽)", callback_data="select_plan:standard")]
                ]

                await query.message.edit_text(
                    "Вы уже использовали пробный период. Выберите один из платных тарифов:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

            # Активируем пробный период
            trial_plan = PRICING_PLANS['trial']

            if not user_credits:
                user_credits = UserCredits(user_id=user_id, credits_remaining=0, has_used_trial=False)
                session.add(user_credits)

            user_credits.credits_remaining += trial_plan['messages']
            user_credits.has_used_trial = True
            session.commit()

            await query.message.edit_text(
                "✅ Пробный период успешно активирован!\n"
                f"Вам доступно {trial_plan['messages']} сообщений.\n"
                "Приятного использования!",
                reply_markup=PaymentKeyboards.get_main_menu_keyboard()
            )

        except Exception as e:
            logger.error(f"Error activating trial: {e}")
            await query.message.edit_text(
                "Произошла ошибка. Пожалуйста, попробуйте позже."
            )

    async def _handle_payment_cancellation(self, query: Update.callback_query):
        """Обработчик отмены платежа"""
        await query.message.edit_text(
            "❌ Оплата отменена.\n"
            "Вы можете выбрать другой тариф или попробовать позже.",
            reply_markup=PaymentKeyboards.get_tariff_selection_keyboard()
        )
