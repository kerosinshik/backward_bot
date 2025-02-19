# middleware/payment_middleware.py

import logging
from functools import wraps
from typing import Callable, Any
from telegram import Update
from telegram.ext import ContextTypes

from backward_bot.config.settings import PAYMENT_MESSAGES, CREDIT_SETTINGS
from backward_bot.services.subscription_service import SubscriptionService
from backward_bot.keyboards.payment_keyboard import PaymentKeyboards

logger = logging.getLogger(__name__)


def check_credits(subscription_service: SubscriptionService) -> Callable:
    """
    Декоратор для проверки наличия кредитов перед обработкой сообщения

    Args:
        subscription_service: Сервис подписок для проверки кредитов

    Returns:
        Callable: Декоратор
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
            if not update.effective_user:
                return

            user_id = update.effective_user.id

            # Проверяем наличие кредитов
            try:
                status = await subscription_service.check_subscription_status(user_id)
                credits_remaining = status['credits_remaining']

                # Если кредиты закончились
                if credits_remaining <= 0:
                    keyboard = PaymentKeyboards.get_tariff_selection_keyboard()
                    await update.message.reply_text(
                        PAYMENT_MESSAGES['no_credits'],
                        reply_markup=keyboard
                    )
                    return

                # Если мало кредитов, предупреждаем
                if credits_remaining <= CREDIT_SETTINGS['min_credits_warning']:
                    await update.message.reply_text(
                        PAYMENT_MESSAGES['low_credits'].format(
                            credits=credits_remaining
                        )
                    )

                # Продолжаем выполнение оригинальной функции
                return await func(update, context, *args, **kwargs)

            except Exception as e:
                logger.error(f"Error in credits check middleware: {e}")
                await update.message.reply_text(
                    "Произошла ошибка при проверке баланса. Пожалуйста, попробуйте позже."
                )
                return

        return wrapper

    return decorator


def track_credit_usage(subscription_service: SubscriptionService, credit_cost: int = 1) -> Callable:
    """
    Декоратор для отслеживания использования кредитов

    Args:
        subscription_service: Сервис подписок для списания кредитов
        credit_cost: Стоимость операции в кредитах

    Returns:
        Callable: Декоратор
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
            if not update.effective_user:
                return

            user_id = update.effective_user.id

            try:
                # Выполняем основную функцию
                result = await func(update, context, *args, **kwargs)

                # Списываем кредиты после успешного выполнения
                await subscription_service.use_credits(user_id, credit_cost)

                return result

            except Exception as e:
                logger.error(f"Error in credit usage tracking: {e}")
                return

        return wrapper

    return decorator


def admin_only(func: Callable) -> Callable:
    """
    Декоратор для ограничения доступа к админским функциям

    Args:
        func: Оригинальная функция

    Returns:
        Callable: Декоратор
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
        if not update.effective_user:
            return

        user_id = update.effective_user.id

        # Проверяем, является ли пользователь администратором
        if not await is_admin(user_id, context):
            await update.message.reply_text(
                "У вас нет прав для выполнения этой команды."
            )
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


async def is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Проверяет, является ли пользователь администратором

    Args:
        user_id: ID пользователя
        context: Контекст Telegram

    Returns:
        bool: Является ли пользователь администратором
    """
    try:
        admin_users = context.bot_data.get('admin_users', [])
        return user_id in admin_users
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


def rate_limit(limit: int, window: int = 60) -> Callable:
    """
    Декоратор для ограничения частоты запросов

    Args:
        limit: Максимальное количество запросов
        window: Временное окно в секундах

    Returns:
        Callable: Декоратор
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
            if not update.effective_user:
                return

            user_id = update.effective_user.id

            # Проверяем ограничение частоты запросов
            rate_key = f"rate_limit_{user_id}"
            user_requests = context.user_data.get(rate_key, [])

            # Очищаем старые запросы
            current_time = context.user_data.get('current_time', 0)
            user_requests = [t for t in user_requests if t > current_time - window]

            if len(user_requests) >= limit:
                await update.message.reply_text(
                    "Слишком много запросов. Пожалуйста, подождите немного."
                )
                return

            # Добавляем текущий запрос
            user_requests.append(current_time)
            context.user_data[rate_key] = user_requests

            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator
