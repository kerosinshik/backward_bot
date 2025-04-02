# handlers/promo_code_handlers.py
import logging
import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config.settings import ADMIN_USERS
from services.promo_code_service import PromoCodeService

logger = logging.getLogger(__name__)


# Асинхронные обертки для синхронных методов PromoCodeService

async def create_promo_code_async(
        session, code, credits, max_uses=None, created_by=None, expires_at=None
):
    """Асинхронная обертка для создания промокода"""
    service = PromoCodeService(session)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.create_promo_code(code, credits, max_uses, created_by, expires_at)
    )
    return result


async def activate_promo_code_async(session, user_id, code):
    """Асинхронная обертка для активации промокода"""
    service = PromoCodeService(session)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.activate_promo_code(user_id, code)
    )
    return result


async def disable_promo_code_async(session, code, admin_id):
    """Асинхронная обертка для деактивации промокода"""
    service = PromoCodeService(session)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.disable_promo_code(code, admin_id)
    )
    return result


async def get_promo_code_stats_async(session, code=None):
    """Асинхронная обертка для получения статистики промокодов"""
    service = PromoCodeService(session)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: service.get_promo_code_stats(code)
    )
    return result


# Обработчики команд

async def handle_promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /promo для активации промокода"""
    user_id = update.effective_user.id

    # Проверяем наличие аргумента (кода промокода)
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "Для активации промокода используйте команду:\n"
            "/promo КОД_ПРОМОКОДА\n\n"
            "Например: /promo LAUNCH100"
        )
        return

    promo_code = context.args[0].upper()  # Преобразуем в верхний регистр для единообразия

    # Активируем промокод
    success, message, credits = await activate_promo_code_async(
        context.bot_data['db_session'],
        user_id,
        promo_code
    )

    if success:
        # Форматируем сообщение об успешной активации
        await update.message.reply_text(
            f"✅ {message}\n\n"
            f"💰 Ваш текущий баланс пополнен на {credits} кредитов.\n"
            f"Используйте /balance для проверки баланса."
        )
    else:
        # Сообщаем об ошибке
        await update.message.reply_text(f"❌ {message}")


async def handle_create_promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /createpromo для создания промокодов (только для админов)"""
    user_id = update.effective_user.id

    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_USERS:
        await update.message.reply_text("⚠️ У вас нет прав для выполнения этой команды.")
        return

    # Проверяем корректность аргументов
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Для создания промокода используйте команду:\n"
            "/createpromo КОД КРЕДИТЫ [МАКС_ИСПОЛЬЗОВАНИЙ] [ДНЕЙ_АКТИВНОСТИ]\n\n"
            "Примеры:\n"
            "/createpromo LAUNCH100 100\n"
            "/createpromo TEST50 50 10\n"
            "/createpromo TEMP20 20 5 30"
        )
        return

    # Парсим аргументы
    code = context.args[0].upper()  # Преобразуем в верхний регистр

    try:
        credits = int(context.args[1])
        if credits <= 0:
            await update.message.reply_text("❌ Количество кредитов должно быть положительным числом.")
            return
    except ValueError:
        await update.message.reply_text("❌ Количество кредитов должно быть числом.")
        return

    # Парсим опциональные аргументы
    max_uses = None
    expires_at = None

    if len(context.args) >= 3:
        try:
            max_uses = int(context.args[2])
            if max_uses <= 0:
                max_uses = None
        except ValueError:
            await update.message.reply_text("❌ Максимальное количество использований должно быть числом.")
            return

    if len(context.args) >= 4:
        try:
            days_valid = int(context.args[3])
            if days_valid > 0:
                expires_at = datetime.utcnow() + timedelta(days=days_valid)
        except ValueError:
            await update.message.reply_text("❌ Количество дней должно быть числом.")
            return

    # Создаем промокод
    success, message = await create_promo_code_async(
        context.bot_data['db_session'],
        code,
        credits,
        max_uses,
        user_id,
        expires_at
    )

    if success:
        # Форматируем сообщение об успешном создании
        expiry_info = f", действует {context.args[3]} дней" if len(context.args) >= 4 else ""
        max_uses_info = f", макс. использований: {max_uses}" if max_uses else ""

        await update.message.reply_text(
            f"✅ {message}\n\n"
            f"📋 Детали промокода:\n"
            f"• Код: {code}\n"
            f"• Кредиты: {credits}{max_uses_info}{expiry_info}"
        )
    else:
        # Сообщаем об ошибке
        await update.message.reply_text(f"❌ {message}")


async def handle_disable_promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /disablepromo для деактивации промокодов (только для админов)"""
    user_id = update.effective_user.id

    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_USERS:
        await update.message.reply_text("⚠️ У вас нет прав для выполнения этой команды.")
        return

    # Проверяем наличие аргумента (кода промокода)
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "Для деактивации промокода используйте команду:\n"
            "/disablepromo КОД_ПРОМОКОДА\n\n"
            "Например: /disablepromo LAUNCH100"
        )
        return

    promo_code = context.args[0].upper()  # Преобразуем в верхний регистр

    # Деактивируем промокод
    success, message = await disable_promo_code_async(
        context.bot_data['db_session'],
        promo_code,
        user_id
    )

    if success:
        await update.message.reply_text(f"✅ {message}")
    else:
        await update.message.reply_text(f"❌ {message}")


async def handle_promostat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /promostat для получения статистики по промокодам (только для админов)"""
    user_id = update.effective_user.id

    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_USERS:
        await update.message.reply_text("⚠️ У вас нет прав для выполнения этой команды.")
        return

    # Проверяем аргументы (опциональный код промокода)
    code = None
    if context.args and len(context.args) > 0:
        code = context.args[0].upper()

    # Получаем статистику
    stats = await get_promo_code_stats_async(
        context.bot_data['db_session'],
        code
    )

    if code and not stats['promo_codes']:
        await update.message.reply_text(f"❌ Промокод '{code}' не найден.")
        return

    # Форматируем статистику
    if code:
        # Детальная статистика по конкретному промокоду
        promo = stats['promo_codes'][0]

        message = [
            f"📊 *Статистика промокода {promo['code']}*\n",
            f"• Кредиты: {promo['credits']}",
            f"• Активен: {'✅' if promo['is_active'] else '❌'}",
            f"• Использований: {promo['used_count']}/{promo['max_uses'] if promo['max_uses'] else '∞'}",
            f"• Уникальных пользователей: {promo['unique_users']}",
            f"• Всего выдано кредитов: {promo['total_credits_granted']}",
            f"• Создан: {promo['created_at'].split('T')[0]}",
        ]

        if promo['expires_at']:
            message.append(f"• Истекает: {promo['expires_at'].split('T')[0]}")

        await update.message.reply_text("\n".join(message), parse_mode='Markdown')
    else:
        # Общая статистика по всем промокодам
        message = [
            f"📊 *Общая статистика промокодов*\n",
            f"• Всего промокодов: {stats['total_codes']}",
            f"• Активных промокодов: {stats['active_codes']}",
            f"• Всего использований: {stats['total_usages']}",
            f"• Всего выдано кредитов: {stats['total_credits_granted']}\n",
            f"*Последние 5 промокодов:*"
        ]

        # Добавляем информацию о последних промокодах
        for promo in stats['promo_codes'][-5:]:
            status = "✅" if promo['is_active'] else "❌"
            message.append(
                f"• {promo['code']}: {promo['credits']} кредитов, "
                f"{promo['used_count']}/{promo['max_uses'] if promo['max_uses'] else '∞'} "
                f"использований {status}"
            )

        # Добавляем инструкцию для получения детальной статистики
        message.append("\nДля детальной статистики по промокоду используйте: /promostat КОД")

        await update.message.reply_text("\n".join(message), parse_mode='Markdown')
