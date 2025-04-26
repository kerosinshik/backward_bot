# handlers/payment_menu_handlers.py
import asyncio
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config.settings import PRICING_PLANS
from services.subscription_service import SubscriptionService
from services.payment_service import PaymentService
from keyboards.payment_keyboard import PaymentKeyboards

logger = logging.getLogger(__name__)


# Асинхронные обертки для синхронных методов

async def get_user_credits_async(session, user_id):
    """Асинхронная обертка для получения кредитов пользователя"""
    service = SubscriptionService(session)
    # Вызываем синхронный метод без await
    result = service.get_user_subscription_status(user_id)
    return result


async def create_payment_async(session, user_id, plan_id):
    """Асинхронная обертка для создания платежа"""
    service = PaymentService(session)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.create_payment(user_id, plan_id)
    )
    return result


async def check_payment_status_async(session, payment_id):
    """Асинхронная обертка для проверки статуса платежа"""
    service = PaymentService(session)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.check_payment_status(payment_id)
    )
    return result


# Обработчики команд

async def handle_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /balance для проверки баланса"""
    user_id = update.effective_user.id

    # Получаем информацию о кредитах пользователя
    subscription_status = await get_user_credits_async(
        context.bot_data['db_session'],
        user_id
    )

    credits_remaining = subscription_status.get('credits_remaining', 0)
    has_active_subscription = subscription_status.get('has_active_subscription', False)
    plan_id = subscription_status.get('plan_id')
    has_used_trial = subscription_status.get('has_used_trial', False)

    # Формируем сообщение о балансе
    message = [
        "💰 *Ваш баланс*\n",
        f"Доступно сообщений: {credits_remaining}",
    ]

    # Добавляем информацию о текущем тарифе
    if has_active_subscription and plan_id:
        plan_name = PRICING_PLANS.get(plan_id, {}).get('name', 'Неизвестный')
        message.append(f"\nАктивный тариф: {plan_name}")

    # Клавиатура с опциями
    keyboard = []

    # Кнопка для пополнения баланса
    keyboard.append([InlineKeyboardButton("💳 Пополнить баланс", callback_data="show_tariffs")])

    # Кнопка для активации пробного тарифа (если еще не использовал)
    if not has_used_trial and credits_remaining == 0:
        keyboard.append([InlineKeyboardButton("🎁 Активировать пробный период", callback_data="activate_trial")])

    # Кнопка для истории операций
    keyboard.append([InlineKeyboardButton("📊 История операций", callback_data="credits_history")])

    await update.message.reply_text(
        "\n".join(message),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_pricing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /pricing для просмотра тарифов"""
    # Получаем информацию о текущих тарифах
    trial_plan = PRICING_PLANS.get('trial', {})
    test_plan = PRICING_PLANS.get('test', {})  # Добавляем тестовый тариф
    basic_plan = PRICING_PLANS.get('basic', {})
    standard_plan = PRICING_PLANS.get('standard', {})

    # Формируем сообщение с описанием тарифов
    message = [
        "💼 *Тарифные планы*\n",
        "Выберите подходящий тариф:\n",
    ]

    # Добавляем описание тарифа Пробный
    message.append(f"🎁 *{trial_plan.get('name', 'Пробный')}*")
    message.append(f"• Сообщений: {trial_plan.get('messages', 20)}")
    message.append(f"• Стоимость: Бесплатно")
    for feature in trial_plan.get('features', []):
        message.append(f"• {feature}")
    message.append("")

    # Добавляем описание тарифа Базовый
    message.append(f"💫 *{basic_plan.get('name', 'Базовый')}*")
    message.append(f"• Сообщений: {basic_plan.get('messages', 100)}")
    message.append(f"• Стоимость: {basic_plan.get('price', 290)}₽")
    for feature in basic_plan.get('features', []):
        message.append(f"• {feature}")
    message.append("")

    # Добавляем описание тарифа Стандарт
    message.append(f"⭐️ *{standard_plan.get('name', 'Стандарт')}*")
    message.append(f"• Сообщений: {standard_plan.get('messages', 300)}")
    message.append(f"• Стоимость: {standard_plan.get('price', 690)}₽")
    for feature in standard_plan.get('features', []):
        message.append(f"• {feature}")

    # Клавиатура с кнопками выбора тарифа
    keyboard = [
        [InlineKeyboardButton("🎁 Пробный (Бесплатно)", callback_data="select_plan:trial")],
        [InlineKeyboardButton(f"💫 Базовый ({basic_plan.get('price', 290)}₽)", callback_data="select_plan:basic")],
        [InlineKeyboardButton(f"⭐️ Стандарт ({standard_plan.get('price', 690)}₽)", callback_data="select_plan:standard")]
    ]

    await update.message.reply_text(
        "\n".join(message),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback-запросов для платежей"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    try:
        # Обработка различных callback-запросов
        if data == "show_tariffs":
            # Показываем меню тарифов
            await handle_show_tariffs(query, context)

        elif data.startswith("select_plan:"):
            # Обработка выбора тарифа
            plan_id = data.split(":")[1]
            await handle_plan_selection(query, context, plan_id)

        elif data == "activate_trial":
            # Активация пробного периода
            await handle_trial_activation(query, context)

        elif data.startswith("create_payment:"):
            # Создание платежа через ЮKassa
            plan_id = data.split(":")[1]
            await handle_create_real_payment(query, context, plan_id)

        elif data.startswith("check_payment:"):
            # Проверка статуса платежа
            payment_id = data.split(":")[1]
            await handle_check_real_payment(query, context, payment_id)

        elif data == "cancel_payment":
            # Отмена платежа
            await query.message.edit_text(
                "❌ Оплата отменена.\n"
                "Вы можете выбрать другой тариф или попробовать позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
                ])
            )

        elif data == "credits_history":
            # Показываем историю операций с кредитами
            await handle_credits_history(query, context)

        elif data == "show_balance":
            # Показываем текущий баланс
            await handle_show_balance(query, context)

    except Exception as e:
        logger.error(f"Ошибка обработки платежного callback: {e}")
        await query.message.edit_text(
            "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Вернуться", callback_data="show_tariffs")]
            ])
        )


# В функции handle_show_tariffs
async def handle_show_tariffs(query, context):
    """Показывает меню выбора тарифов"""
    # Получаем информацию о текущих тарифах
    trial_plan = PRICING_PLANS.get('trial', {})
    basic_plan = PRICING_PLANS.get('basic', {})
    standard_plan = PRICING_PLANS.get('standard', {})

    # Формируем сообщение с описанием тарифов
    message = [
        "💼 *Тарифные планы*\n",
        "Выберите подходящий тариф:\n",
    ]

    # Добавляем описания тарифов...
    message.append(f"🎁 *{trial_plan.get('name', 'Пробный')}*")
    message.append(f"• Сообщений: {trial_plan.get('messages', 20)}")
    message.append(f"• Стоимость: Бесплатно\n")

    message.append(f"💫 *{basic_plan.get('name', 'Базовый')}*")
    message.append(f"• Сообщений: {basic_plan.get('messages', 100)}")
    message.append(f"• Стоимость: {basic_plan.get('price', 290)}₽\n")

    message.append(f"⭐️ *{standard_plan.get('name', 'Стандарт')}*")
    message.append(f"• Сообщений: {standard_plan.get('messages', 300)}")
    message.append(f"• Стоимость: {standard_plan.get('price', 690)}₽")

    # Клавиатура с кнопками выбора тарифа
    keyboard = [
        [InlineKeyboardButton("🎁 Пробный (Бесплатно)", callback_data="select_plan:trial")],
        [InlineKeyboardButton(f"💫 Базовый ({basic_plan.get('price', 290)}₽)", callback_data="select_plan:basic")],
        [InlineKeyboardButton(f"⭐️ Стандарт ({standard_plan.get('price', 690)}₽)",
                              callback_data="select_plan:standard")]
    ]

    await query.message.edit_text(
        "\n".join(message),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_show_balance(query, context):
    """Показывает информацию о текущем балансе"""
    user_id = query.from_user.id

    # Получаем информацию о кредитах пользователя
    subscription_status = await get_user_credits_async(
        context.bot_data['db_session'],
        user_id
    )

    credits_remaining = subscription_status.get('credits_remaining', 0)
    has_active_subscription = subscription_status.get('has_active_subscription', False)
    plan_id = subscription_status.get('plan_id')
    has_used_trial = subscription_status.get('has_used_trial', False)

    # Формируем сообщение о балансе
    message = [
        "💰 *Ваш баланс*\n",
        f"Доступно сообщений: {credits_remaining}",
    ]

    # Добавляем информацию о текущем тарифе
    if has_active_subscription and plan_id:
        plan_name = PRICING_PLANS.get(plan_id, {}).get('name', 'Неизвестный')
        message.append(f"\nАктивный тариф: {plan_name}")

    # Клавиатура с опциями
    keyboard = []

    # Кнопка для пополнения баланса
    keyboard.append([InlineKeyboardButton("💳 Пополнить баланс", callback_data="show_tariffs")])

    # Кнопка для активации пробного тарифа (если еще не использовал)
    if not has_used_trial and credits_remaining == 0:
        keyboard.append([InlineKeyboardButton("🎁 Активировать пробный период", callback_data="activate_trial")])

    # Кнопка для истории операций
    keyboard.append([InlineKeyboardButton("📊 История операций", callback_data="credits_history")])

    await query.message.edit_text(
        "\n".join(message),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_plan_selection(query, context, plan_id):
    """Обрабатывает выбор тарифа"""
    user_id = query.from_user.id

    # Получаем информацию о выбранном тарифе
    plan = PRICING_PLANS.get(plan_id)

    if not plan:
        await query.message.edit_text("❌ Выбранный тариф не найден.")
        return

    # Проверяем, выбран ли пробный тариф
    if plan_id == 'trial':
        # Проверяем, использовал ли пользователь пробный период
        subscription_status = await get_user_credits_async(
            context.bot_data['db_session'],
            user_id
        )

        has_used_trial = subscription_status.get('has_used_trial', False)

        if has_used_trial:
            # Если пробный период уже использован
            keyboard = [
                [InlineKeyboardButton(f"💫 Базовый ({PRICING_PLANS['basic']['price']}₽)",
                                      callback_data="select_plan:basic")],
                [InlineKeyboardButton(f"⭐️ Стандарт ({PRICING_PLANS['standard']['price']}₽)",
                                      callback_data="select_plan:standard")],
                [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
            ]

            await query.message.edit_text(
                "⚠️ Вы уже использовали пробный период.\n\n"
                "Выберите один из доступных тарифов:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Если пробный период не использован
        keyboard = [
            [InlineKeyboardButton("✨ Активировать пробный период", callback_data="activate_trial")],
            [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
        ]

        await query.message.edit_text(
            f"🎁 *Пробный тариф*\n\n"
            f"• {plan['messages']} сообщений\n"
            f"• Без срока действия\n"
            f"• Для знакомства с сервисом\n\n"
            f"Активировать пробный период?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Для платных тарифов
    keyboard = [
        [InlineKeyboardButton(f"💳 Оплатить {plan['price']}₽", callback_data=f"create_payment:{plan_id}")],
        [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
    ]

    features_text = "\n".join([f"• {feature}" for feature in plan.get('features', [])])

    await query.message.edit_text(
        f"*{plan['name']} тариф*\n\n"
        f"• {plan['messages']} сообщений\n"
        f"• Стоимость: {plan['price']}₽\n\n"
        f"{features_text}\n\n"
        f"Перейти к оплате?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_trial_activation(query, context):
    """Обрабатывает активацию пробного периода"""
    user_id = query.from_user.id

    # Активируем пробный период
    session = context.bot_data['db_session']
    subscription_service = SubscriptionService(session)

    result = subscription_service.activate_subscription(user_id, 'trial')

    if result:
        await query.message.edit_text(
            "✅ *Пробный период успешно активирован!*\n\n"
            "Вам доступно 20 сообщений.\n"
            "Приятного использования!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.message.edit_text(
            "❌ Произошла ошибка при активации пробного периода.\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )


async def handle_create_real_payment(query, context, plan_id):
    """Обрабатывает создание реального платежа через ЮKassa"""
    user_id = query.from_user.id

    # Получаем информацию о тарифе
    plan = PRICING_PLANS.get(plan_id)

    if not plan:
        await query.message.edit_text("❌ Выбранный тариф не найден.")
        return

    # Показываем сообщение о создании платежа
    await query.message.edit_text(
        "⏳ Создаем платеж...\n\n"
        "Пожалуйста, подождите..."
    )

    # Создаем платеж через ЮKassa
    payment_result = await create_payment_async(
        context.bot_data['db_session'],
        user_id,
        plan_id
    )

    if "error" in payment_result:
        # В случае ошибки
        await query.message.edit_text(
            f"❌ Ошибка создания платежа: {payment_result['error']}\n\n"
            f"Пожалуйста, попробуйте позже или выберите другой тариф.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
            ])
        )
        return

    # Успешное создание платежа
    payment_id = payment_result.get("payment_id")
    payment_url = payment_result.get("payment_url")

    # Клавиатура для перехода к оплате и проверки статуса
    keyboard = [
        [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
        [InlineKeyboardButton("🔄 Проверить статус оплаты", callback_data=f"check_payment:{payment_id}")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment")]
    ]

    await query.message.edit_text(
        f"✅ *Платеж создан*\n\n"
        f"Тариф: {plan['name']}\n"
        f"Сообщений: {plan['messages']}\n"
        f"Стоимость: {plan['price']}₽\n\n"
        f"Для оплаты нажмите кнопку «Перейти к оплате».\n"
        f"После завершения оплаты вернитесь в чат и нажмите «Проверить статус оплаты».",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_check_real_payment(query, context, payment_id):
    """Обрабатывает проверку статуса реального платежа"""
    user_id = query.from_user.id

    # Показываем сообщение о проверке
    await query.message.edit_text(
        "⏳ Проверяем статус платежа...\n\n"
        "Пожалуйста, подождите..."
    )

    # Проверяем статус платежа
    payment_status = await check_payment_status_async(
        context.bot_data['db_session'],
        payment_id
    )

    if "error" in payment_status:
        # В случае ошибки
        await query.message.edit_text(
            f"❌ Ошибка проверки статуса: {payment_status['error']}\n\n"
            f"Пожалуйста, попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить еще раз", callback_data=f"check_payment:{payment_id}")],
                [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
            ])
        )
        return

    # Получаем статус платежа
    status = payment_status.get("status", "pending")
    paid = payment_status.get("paid", False)

    # Клавиатура для повторной проверки
    retry_keyboard = [
        [InlineKeyboardButton("🔄 Проверить еще раз", callback_data=f"check_payment:{payment_id}")],
        [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
    ]

    # Обрабатываем разные статусы
    if status == "succeeded" and paid:
        # Платеж успешно завершен
        # Получаем информацию о тарифе из метаданных платежа
        plan_id = payment_status.get("description", "").split(" ")[2] if "description" in payment_status else "unknown"
        plan = PRICING_PLANS.get(plan_id, {})
        plan_name = plan.get('name', 'Неизвестный')

        await query.message.edit_text(
            f"✅ *Платеж успешно завершен!*\n\n"
            f"Тариф: {plan_name}\n"
            f"Ваш баланс пополнен.\n\n"
            f"Приятного использования!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Проверить баланс", callback_data="show_balance")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
    elif status == "canceled":
        # Платеж отменен
        await query.message.edit_text(
            "❌ *Платеж отменен*\n\n"
            "Вы можете попробовать снова или выбрать другой тариф.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Назад к тарифам", callback_data="show_tariffs")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
    elif status == "pending":
        # Платеж в обработке
        await query.message.edit_text(
            "⏳ *Платеж в обработке*\n\n"
            "Ваш платеж еще не завершен. Если вы уже оплатили, то обработка может занять некоторое время.\n\n"
            "Нажмите «Проверить еще раз» через несколько минут.",
            reply_markup=InlineKeyboardMarkup(retry_keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    elif status == "waiting_for_capture":
        # Платеж ожидает подтверждения
        await query.message.edit_text(
            "⏳ *Платеж ожидает подтверждения*\n\n"
            "Ваш платеж находится в процессе подтверждения. Это может занять некоторое время.\n\n"
            "Нажмите «Проверить еще раз» через несколько минут.",
            reply_markup=InlineKeyboardMarkup(retry_keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Другие статусы
        await query.message.edit_text(
            f"ℹ️ *Статус платежа: {status}*\n\n"
            f"Ваш платеж находится в обработке. Пожалуйста, проверьте статус позже.",
            reply_markup=InlineKeyboardMarkup(retry_keyboard),
            parse_mode=ParseMode.MARKDOWN
        )


async def handle_credits_history(query, context):
    """Показывает историю операций с кредитами"""
    user_id = query.from_user.id

    # Получаем историю платежей
    service = PaymentService(context.bot_data['db_session'])

    # Используем run_in_executor для вызова синхронного метода
    loop = asyncio.get_running_loop()
    payment_history = await loop.run_in_executor(
        None,
        lambda: service.get_payment_history(user_id)
    )

    # Проверяем, есть ли история
    payments = payment_history.get('payments', [])

    if not payments:
        # Если история пуста
        await query.message.edit_text(
            "📊 *История операций*\n\n"
            "У вас пока нет операций с кредитами.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Назад к балансу", callback_data="show_balance")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Формируем сообщение с историей
    message = ["📊 *История операций*\n"]

    for payment in payments:
        plan_id = payment.get('plan_id', 'unknown')
        plan = PRICING_PLANS.get(plan_id, {})
        plan_name = plan.get('name', 'Неизвестный')
        status = payment.get('status', 'unknown')
        amount = payment.get('amount', 0)
        credits = plan.get('messages', 0)

        # Форматируем дату
        created_at = datetime.fromisoformat(payment.get('created_at', '').replace('Z', '+00:00')) \
            if payment.get('created_at') else None
        date_str = created_at.strftime('%d.%m.%Y %H:%M') if created_at else 'Неизвестно'

        # Определяем статус для отображения
        status_emoji = "✅" if status == "succeeded" else "⏳" if status == "pending" else "❌"
        status_text = "Успешно" if status == "succeeded" else "В обработке" if status == "pending" else "Отменено"

        message.append(
            f"{status_emoji} *{date_str}*\n"
            f"Тариф: {plan_name} ({credits} сообщений)\n"
            f"Сумма: {amount}₽\n"
            f"Статус: {status_text}\n"
        )

        # Добавляем кнопку возврата
        keyboard = [
            [InlineKeyboardButton("« Назад к балансу", callback_data="show_balance")]
        ]

        await query.message.edit_text(
            "\n".join(message),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
