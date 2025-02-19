# handlers/payment_webhook.py

import hmac
import hashlib
import base64
import json
import logging
from typing import Dict, Any, Optional
from aiohttp import web
from datetime import datetime

from config.settings import YOOKASSA_SECRET_KEY, PAYMENT_MESSAGES
from services.payment_service import PaymentService
from database.models import PaymentHistory

logger = logging.getLogger(__name__)


class PaymentWebhookHandler:
    """Обработчик вебхуков от ЮKassa"""

    def __init__(self, payment_service: PaymentService, bot):
        """
        Инициализация обработчика вебхуков

        Args:
            payment_service: Сервис для работы с платежами
            bot: Экземпляр бота для отправки уведомлений
        """
        self.payment_service = payment_service
        self.bot = bot

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """
        Обработчик POST-запросов от ЮKassa

        Args:
            request: Входящий HTTP-запрос

        Returns:
            web.Response: HTTP-ответ
        """
        try:
            # Проверяем подпись запроса
            if not await self._verify_signature(request):
                logger.warning("Invalid webhook signature")
                return web.Response(status=400, text="Invalid signature")

            # Получаем данные запроса
            payload = await request.json()
            logger.info(f"Received webhook: {json.dumps(payload, indent=2)}")

            # Обрабатываем уведомление
            await self._process_notification(payload)

            return web.Response(status=200, text="OK")

        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return web.Response(status=500, text="Internal server error")

    async def _verify_signature(self, request: web.Request) -> bool:
        """
        Проверяет подпись запроса от ЮKassa

        Args:
            request: Входящий HTTP-запрос

        Returns:
            bool: Результат проверки подписи
        """
        try:
            signature = request.headers.get('X-YooKassa-Signature')
            if not signature:
                return False

            body = await request.read()
            secret_key = YOOKASSA_SECRET_KEY.encode('utf-8')

            hmac_obj = hmac.new(secret_key, body, hashlib.sha256)
            calculated_signature = base64.b64encode(hmac_obj.digest()).decode('utf-8')

            return hmac.compare_digest(signature, calculated_signature)

        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False

    async def _process_notification(self, payload: Dict[str, Any]):
        """
        Обрабатывает уведомление о платеже

        Args:
            payload: Данные уведомления
        """
        try:
            event = payload.get('event')
            payment = payload.get('object', {})
            payment_id = payment.get('id')

            if not all([event, payment, payment_id]):
                logger.error("Invalid webhook payload structure")
                return

            metadata = payment.get('metadata', {})
            user_id = int(metadata.get('user_id', 0))

            if not user_id:
                logger.error(f"No user_id in payment {payment_id} metadata")
                return

            # Обрабатываем различные события
            if event == 'payment.succeeded':
                await self._handle_successful_payment(payment_id, user_id, payment)
            elif event == 'payment.canceled':
                await self._handle_canceled_payment(payment_id, user_id)
            elif event == 'payment.waiting_for_capture':
                await self._handle_waiting_payment(payment_id, user_id)
            else:
                logger.warning(f"Unhandled payment event: {event}")

        except Exception as e:
            logger.error(f"Error processing notification: {e}")

    async def _handle_successful_payment(self, payment_id: str, user_id: int,
                                         payment_data: Dict[str, Any]):
        """
        Обрабатывает успешный платеж

        Args:
            payment_id: ID платежа
            user_id: ID пользователя
            payment_data: Данные платежа
        """
        try:
            # Обновляем статус платежа
            await self.payment_service.process_successful_payment(payment_id)

            # Отправляем уведомление пользователю
            amount = payment_data.get('amount', {}).get('value', '0')
            message = (
                f"{PAYMENT_MESSAGES['payment_success']}\n"
                f"Сумма: {amount}₽\n"
                f"ID платежа: {payment_id}"
            )

            await self.bot.send_message(
                chat_id=user_id,
                text=message
            )

        except Exception as e:
            logger.error(f"Error handling successful payment: {e}")

    async def _handle_canceled_payment(self, payment_id: str, user_id: int):
        """
        Обрабатывает отмененный платеж

        Args:
            payment_id: ID платежа
            user_id: ID пользователя
        """
        try:
            # Обновляем статус платежа в БД
            payment_history = self.payment_service.session.query(PaymentHistory) \
                .filter_by(payment_id=payment_id) \
                .first()

            if payment_history:
                payment_history.status = 'canceled'
                payment_history.updated_at = datetime.utcnow()
                self.payment_service.session.commit()

            # Отправляем уведомление пользователю
            await self.bot.send_message(
                chat_id=user_id,
                text=PAYMENT_MESSAGES['payment_cancelled']
            )

        except Exception as e:
            logger.error(f"Error handling canceled payment: {e}")

    async def _handle_waiting_payment(self, payment_id: str, user_id: int):
        """
        Обрабатывает платеж в ожидании подтверждения

        Args:
            payment_id: ID платежа
            user_id: ID пользователя
        """
        try:
            # Обновляем статус платежа в БД
            payment_history = self.payment_service.session.query(PaymentHistory) \
                .filter_by(payment_id=payment_id) \
                .first()

            if payment_history:
                payment_history.status = 'waiting'
                payment_history.updated_at = datetime.utcnow()
                self.payment_service.session.commit()

            # Отправляем уведомление пользователю
            await self.bot.send_message(
                chat_id=user_id,
                text=PAYMENT_MESSAGES['payment_pending']
            )

        except Exception as e:
            logger.error(f"Error handling waiting payment: {e}")
