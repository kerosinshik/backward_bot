# handlers/yookassa_webhook_handler.py
import logging
import json
import asyncio
from typing import Dict, Any, Callable

from aiohttp import web
from telegram import Bot

from services.payment_service import PaymentService
from config.settings import ADMIN_USERS
from database.models import PaymentHistory

logger = logging.getLogger(__name__)


class YooKassaWebhookHandler:
    """
    Обработчик webhook-уведомлений от ЮKassa
    """

    def __init__(self, bot: Bot, payment_service: PaymentService):
        """
        Инициализация обработчика webhook

        Args:
            bot: Экземпляр бота Telegram
            payment_service: Сервис для работы с платежами
        """
        self.bot = bot
        self.payment_service = payment_service

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """
        Обработчик webhook-уведомлений от ЮKassa

        Args:
            request: Запрос с данными уведомления

        Returns:
            Ответ с кодом 200 при успешной обработке
        """
        try:
            # Логируем все заголовки запроса для диагностики
            logger.info(f"Получен webhook-запрос от ЮKassa. Заголовки: {dict(request.headers)}")

            # Получаем тело запроса
            body = await request.read()
            body_text = body.decode('utf-8', errors='replace')
            logger.info(f"Тело webhook-запроса: {body_text}")

            # Проверяем подпись, если она есть
            signature = request.headers.get('X-YooKassa-Signature')
            if signature:
                logger.info(f"Получена подпись webhook: {signature}")
                signature_valid = self.payment_service.verify_webhook_signature(body, signature)
                logger.info(f"Результат проверки подписи: {'Успешно' if signature_valid else 'Неверная подпись'}")

                if not signature_valid:
                    logger.warning("Неверная подпись webhook - отклоняем запрос")
                    return web.Response(status=400, text="Invalid signature")
            else:
                logger.warning("Webhook без подписи - продолжаем в тестовом режиме")
                # В тестовом режиме можно продолжить без подписи
                # На продакшене лучше включить эту проверку:
                # return web.Response(status=400, text="Signature required")

            # Парсим JSON из тела запроса
            try:
                payload = json.loads(body_text)
                logger.info(f"JSON успешно разобран: {json.dumps(payload, ensure_ascii=False)}")
            except json.JSONDecodeError as json_err:
                logger.error(f"Ошибка разбора JSON: {json_err}. Тело запроса: {body_text[:200]}...")
                return web.Response(status=400, text=f"Invalid JSON: {str(json_err)}")

            # Проверяем обязательные поля в запросе
            if 'event' not in payload or 'object' not in payload:
                logger.error(f"Отсутствуют обязательные поля в запросе: {payload}")
                return web.Response(status=400, text="Missing required fields")

            # Получаем данные о событии
            event_type = payload.get('event')
            payment_data = payload.get('object', {})
            payment_id = payment_data.get('id')
            metadata = payment_data.get('metadata', {})

            logger.info(f"Тип события: {event_type}, ID платежа: {payment_id}, Метаданные: {metadata}")

            # Обрабатываем уведомление
            logger.info("Начинаем обработку webhook-уведомления")
            success, message = self.payment_service.process_webhook_notification(payload)
            logger.info(f"Результат обработки: {'Успешно' if success else 'Ошибка'}, Сообщение: {message}")

            # После обработки уведомляем пользователя и администратора
            if success:
                # Создаем задачу для асинхронных уведомлений
                asyncio.create_task(self._notify_user_about_payment(payload))
                asyncio.create_task(self._notify_admin_about_payment(payload))

            if success:
                return web.Response(status=200, text="OK")
            else:
                logger.error(f"Ошибка обработки webhook: {message}")
                return web.Response(status=400, text=message)

        except Exception as e:
            # Подробное логирование исключения со стеком вызова
            logger.error(f"Необработанное исключение при обработке webhook: {e}", exc_info=True)
            return web.Response(status=500, text=f"Internal Server Error: {str(e)}")

    async def _process_webhook_async(self, payload: Dict[str, Any]) -> tuple:
        """
        Асинхронная обработка webhook-уведомления

        Args:
            payload: Данные уведомления

        Returns:
            Кортеж (успех, сообщение)
        """
        # Используем thread_pool для запуска синхронного метода
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.payment_service.process_webhook_notification(payload)
        )

        # После обработки уведомления, отправляем сообщение пользователю
        if result[0]:  # Если успешно обработали
            await self._notify_user_about_payment(payload)
            await self._notify_admin_about_payment(payload)

        return result

    async def _notify_user_about_payment(self, payload: Dict[str, Any]):
        """
        Отправка уведомления пользователю о статусе платежа

        Args:
            payload: Данные уведомления
        """
        try:
            # Получаем информацию о платеже
            event = payload.get('event')
            payment_data = payload.get('object', {})
            payment_id = payment_data.get('id')
            metadata = payment_data.get('metadata', {})

            # Пытаемся получить данные из метаданных
            user_id = None
            plan_id = None

            # Сначала проверяем метаданные из webhook
            if metadata:
                user_id = int(metadata.get('user_id', 0))
                plan_id = metadata.get('plan_id')

            # Если метаданные отсутствуют, пытаемся найти платеж в БД
            if not user_id or not plan_id:
                logger.info(
                    f"Метаданные отсутствуют в webhook. Пытаемся получить данные из БД для платежа {payment_id}")

                # Получаем сессию из payment_service
                session = self.payment_service.session
                payment_record = session.query(PaymentHistory).filter_by(payment_id=payment_id).first()

                if payment_record:
                    logger.info(
                        f"Найдена запись платежа в БД: ID пользователя={payment_record.user_id}, Тариф={payment_record.plan_id}")
                    user_id = payment_record.user_id
                    plan_id = payment_record.plan_id
                else:
                    logger.warning(f"Платеж {payment_id} не найден в базе данных")
                    return

            # Если не удалось получить ID пользователя, прекращаем обработку
            if not user_id:
                logger.warning(f"ID пользователя не найден для платежа {payment_id}")
                return

            # Формируем сообщение в зависимости от типа события
            if event == 'payment.succeeded':
                from backward_bot.config.settings import PRICING_PLANS
                plan = PRICING_PLANS.get(plan_id, {})
                plan_name = plan.get('name', 'Неизвестный')
                messages_count = plan.get('messages', 0)

                message = (
                    f"✅ *Платеж успешно выполнен!*\n\n"
                    f"Тариф: {plan_name}\n"
                    f"Количество сообщений: {messages_count}\n"
                    f"Сумма: {payment_data.get('amount', {}).get('value', '0')} "
                    f"{payment_data.get('amount', {}).get('currency', 'RUB')}\n\n"
                    f"Ваш баланс пополнен. Приятного использования!"
                )
                logger.info(f"Отправляем уведомление об успешной оплате пользователю {user_id}, тариф {plan_id}")

            elif event == 'payment.canceled':
                message = (
                    f"❌ *Платеж отменен*\n\n"
                    f"К сожалению, ваш платеж был отменен.\n"
                    f"Вы можете попробовать снова или выбрать другой способ оплаты."
                )
                logger.info(f"Отправляем уведомление об отмене платежа пользователю {user_id}")

            elif event == 'payment.waiting_for_capture':
                message = (
                    f"⏳ *Платеж в обработке*\n\n"
                    f"Ваш платеж находится в обработке.\n"
                    f"Мы уведомим вас, когда он будет завершен."
                )
                logger.info(f"Отправляем уведомление о платеже в обработке пользователю {user_id}")

            else:
                # Другие события не отправляем пользователю
                return

            # Отправляем сообщение пользователю
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"Отправлено уведомление пользователю {user_id} о событии {event}")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления пользователю: {e}", exc_info=True)

    async def _notify_admin_about_payment(self, payload: Dict[str, Any]):
        """
        Отправка уведомления администраторам о платеже

        Args:
            payload: Данные уведомления
        """
        try:
            # Получаем информацию о платеже
            event = payload.get('event')
            payment_data = payload.get('object', {})
            payment_id = payment_data.get('id')
            metadata = payment_data.get('metadata', {})
            user_id = metadata.get('user_id', 'неизвестно')
            plan_id = metadata.get('plan_id', 'неизвестно')

            # Формируем сообщение для администратора
            message = (
                f"💰 *Уведомление о платеже*\n\n"
                f"Событие: {event}\n"
                f"ID платежа: {payment_id}\n"
                f"Пользователь: {user_id}\n"
                f"Тариф: {plan_id}\n"
                f"Сумма: {payment_data.get('amount', {}).get('value', '0')} "
                f"{payment_data.get('amount', {}).get('currency', 'RUB')}\n"
                f"Статус: {payment_data.get('status', 'неизвестно')}"
            )

            # Отправляем сообщение всем администраторам
            for admin_id in ADMIN_USERS:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                except Exception as admin_error:
                    logger.error(f"Не удалось отправить уведомление администратору {admin_id}: {admin_error}")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления администраторам: {e}")


def setup_webhook_routes(app: web.Application, webhook_handler: YooKassaWebhookHandler):
    """
    Настройка маршрутов для webhook

    Args:
        app: Приложение aiohttp
        webhook_handler: Обработчик webhook
    """
    app.router.add_post('/webhook/yookassa', webhook_handler.handle_webhook)
    logger.info("Маршруты webhook настроены")
