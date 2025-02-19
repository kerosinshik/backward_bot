# keyboards/payment_keyboard.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Dict
from backward_bot.config.settings import PRICING_PLANS


class PaymentKeyboards:
    """Класс для создания клавиатур платежного интерфейса"""

    @staticmethod
    def get_tariff_selection_keyboard() -> InlineKeyboardMarkup:
        """
        Создает клавиатуру выбора тарифа с подробным описанием

        Returns:
            InlineKeyboardMarkup: Клавиатура с тарифами
        """
        keyboard = []

        # Пробный тариф
        trial_btn = InlineKeyboardButton(
            "🎁 Пробный тариф (Бесплатно)",
            callback_data="select_plan:trial"
        )
        keyboard.append([trial_btn])

        # Базовый тариф
        basic_btn = InlineKeyboardButton(
            "💫 Базовый тариф - 290₽",
            callback_data="select_plan:basic"
        )
        keyboard.append([basic_btn])

        # Стандартный тариф
        standard_btn = InlineKeyboardButton(
            "⭐️ Стандарт тариф - 690₽",
            callback_data="select_plan:standard"
        )
        keyboard.append([standard_btn])

        # Информация о тарифах
        info_btn = InlineKeyboardButton(
            "ℹ️ Подробнее о тарифах",
            callback_data="tariff_info"
        )
        keyboard.append([info_btn])

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_plan_details_keyboard(plan_id: str) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру с подробной информацией о тарифе

        Args:
            plan_id: Идентификатор тарифа

        Returns:
            InlineKeyboardMarkup: Клавиатура с информацией о тарифе
        """
        keyboard = []

        # Кнопка покупки
        if plan_id != 'trial':
            buy_btn = InlineKeyboardButton(
                f"💳 Оплатить {PRICING_PLANS[plan_id]['price']}₽",
                callback_data=f"buy_plan:{plan_id}"
            )
            keyboard.append([buy_btn])
        else:
            activate_btn = InlineKeyboardButton(
                "✨ Активировать пробный период",
                callback_data="activate_trial"
            )
            keyboard.append([activate_btn])

        # Кнопка возврата к списку тарифов
        back_btn = InlineKeyboardButton(
            "« Назад к тарифам",
            callback_data="show_tariffs"
        )
        keyboard.append([back_btn])

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_payment_confirmation_keyboard(payment_url: str) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для подтверждения оплаты

        Args:
            payment_url: URL для оплаты от ЮKassa

        Returns:
            InlineKeyboardMarkup: Клавиатура с кнопками оплаты
        """
        keyboard = [
            [
                InlineKeyboardButton(
                    "💳 Перейти к оплате",
                    url=payment_url
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Проверить оплату",
                    callback_data="check_payment"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Отменить",
                    callback_data="cancel_payment"
                )
            ]
        ]

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_payment_status_keyboard() -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для просмотра статуса платежа

        Returns:
            InlineKeyboardMarkup: Клавиатура со статусом
        """
        keyboard = [
            [
                InlineKeyboardButton(
                    "🔄 Обновить статус",
                    callback_data="refresh_payment"
                )
            ],
            [
                InlineKeyboardButton(
                    "« Назад к тарифам",
                    callback_data="show_tariffs"
                )
            ]
        ]

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_credits_info_keyboard() -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для просмотра информации о кредитах

        Returns:
            InlineKeyboardMarkup: Клавиатура с информацией о кредитах
        """
        keyboard = [
            [
                InlineKeyboardButton(
                    "💳 Пополнить баланс",
                    callback_data="show_tariffs"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 История операций",
                    callback_data="credits_history"
                )
            ]
        ]

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_payment_history_keyboard() -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для просмотра истории платежей

        Returns:
            InlineKeyboardMarkup: Клавиатура с историей платежей
        """
        keyboard = [
            [
                InlineKeyboardButton(
                    "📥 Скачать историю",
                    callback_data="download_history"
                )
            ],
            [
                InlineKeyboardButton(
                    "« Назад",
                    callback_data="credits_info"
                )
            ]
        ]

        return InlineKeyboardMarkup(keyboard)
