# services/payment_service.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from yookassa import Payment, Configuration

from database.models import (
    PaymentHistory,
    UserPseudonym,
    UserCredits
)
from config.settings import (
    ANONYMIZATION_SETTINGS,
    PAYMENT_SETTINGS,
    PRICING_PLANS,
    YOOKASSA_SHOP_ID,
    YOOKASSA_SECRET_KEY,
    BOT_USERNAME
)
from services.encryption_service import EncryptionService
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Сервис для работы с платежами через ЮKassa
    """

    def __init__(
            self,
            session: Session,
            encryption_service: Optional[EncryptionService] = None,
            subscription_service: Optional[SubscriptionService] = None
    ):
        """
        Инициализация сервиса платежей

        Args:
            session: Сессия SQLAlchemy
            encryption_service: Сервис шифрования (создается при необходимости)
            subscription_service: Сервис подписок (создается при необходимости)
        """
        self.session = session
        self.encryption_service = encryption_service or EncryptionService(session)
        self.subscription_service = subscription_service or SubscriptionService(session, encryption_service)

        # Настройки конфиденциальности
        self.pseudonymize = ANONYMIZATION_SETTINGS.get(
            'enable_pseudonymization',
            True
        )

        # Конфигурация ЮKassa
        try:
            Configuration.account_id = YOOKASSA_SHOP_ID
            Configuration.secret_key = YOOKASSA_SECRET_KEY
            logger.info("ЮKassa API успешно сконфигурирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации ЮKassa API: {e}")

    def create_payment(
            self,
            user_id: int,
            plan_id: str
    ) -> Dict[str, Any]:
        """
        Создание платежа через ЮKassa

        Args:
            user_id: ID пользователя
            plan_id: Идентификатор тарифного плана

        Returns:
            Словарь с информацией о платеже
        """
        try:
            # Получаем pseudonym_id
            pseudonym_id = self.encryption_service.ensure_pseudonym(user_id)

            # Проверяем план
            plan = PRICING_PLANS.get(plan_id)
            if not plan:
                logger.warning(f"Invalid plan_id: {plan_id}")
                return {"error": "Неверный тарифный план"}

            # Генерируем идентификатор платежа
            payment_id = str(uuid.uuid4())

            try:
                # Создаем платеж через ЮKassa
                payment_data = {
                    "amount": {
                        "value": str(plan['price']),
                        "currency": PAYMENT_SETTINGS.get('currency', 'RUB')
                    },
                    "confirmation": {
                        "type": "redirect",
                        "return_url": f"https://t.me/{BOT_USERNAME}"
                    },
                    "description": f"Оплата тарифа {plan['name']} ({plan['messages']} сообщений)",
                    "metadata": {
                        "user_id": str(user_id),
                        "pseudonym_id": pseudonym_id,
                        "plan_id": plan_id
                    },
                    "receipt": {
                        "customer": {
                            "email": "client@example.com"  # Временный email для тестирования
                        },
                        "items": [
                            {
                                "description": f"Тариф {plan['name']} ({plan['messages']} сообщений)",
                                "quantity": "1.00",
                                "amount": {
                                    "value": str(plan['price']),
                                    "currency": PAYMENT_SETTINGS.get('currency', 'RUB')
                                },
                                "vat_code": "1",  # НДС 20%
                                "payment_subject": "service",
                                "payment_mode": "full_payment"
                            }
                        ]
                    },
                    "capture": True,
                    "save_payment_method": False
                }

                # Логируем содержимое запроса
                logger.info(f"Создаем платеж в ЮKassa с данными: {payment_data}")

                payment = Payment.create(payment_data)

            except Exception as yookassa_error:
                # Логируем подробную информацию об ошибке
                logger.error(f"Ошибка при создании платежа в ЮKassa: {yookassa_error}")
                logger.error(f"Детали ошибки: {str(yookassa_error)}")
                # Пытаемся получить более подробную информацию об ошибке
                detailed_error = yookassa_error.response.text if hasattr(yookassa_error,
                                                                         'response') else 'Нет текста ошибки'
                logger.error(f"Полный текст ошибки: {detailed_error}")
                return {"error": f"Ошибка платежного сервиса: {str(yookassa_error)}"}

            # Сохраняем информацию о платеже в базе данных
            # ВАЖНОЕ ИЗМЕНЕНИЕ: Всегда передаем user_id, независимо от pseudonymize
            payment_record = PaymentHistory(
                user_id=user_id,  # Всегда передаем реальный user_id
                payment_id=payment.id,  # Используем ID из ЮKassa
                amount=float(plan['price']),
                plan_id=plan_id,
                status='pending',
                created_at=datetime.utcnow()
            )
            self.session.add(payment_record)
            self.session.commit()

            return {
                "pseudonym_id": pseudonym_id,
                "payment_id": payment.id,
                "payment_url": payment.confirmation.confirmation_url,
                "status": payment.status
            }

        except Exception as e:
            logger.error(f"Ошибка создания платежа: {e}")
            self.session.rollback()
            return {"error": "Внутренняя ошибка создания платежа"}

    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Проверка статуса платежа в ЮKassa

        Args:
            payment_id: ID платежа

        Returns:
            Словарь со статусом платежа
        """
        try:
            # Получаем информацию о платеже из ЮKassa
            payment = Payment.find_one(payment_id)

            # Обновляем статус платежа в базе данных
            payment_record = self.session.query(PaymentHistory).filter_by(payment_id=payment_id).first()

            if payment_record:
                # Обновляем статус
                payment_record.status = payment.status
                payment_record.updated_at = datetime.utcnow()
                self.session.commit()

                # Если платеж успешен, активируем тариф
                if payment.status == 'succeeded' and payment_record.status != 'succeeded':
                    # Получаем информацию о пользователе и плане из платежа
                    metadata = payment.metadata or {}
                    user_id = int(metadata.get('user_id', 0))
                    plan_id = metadata.get('plan_id')

                    if user_id and plan_id:
                        # Активируем подписку
                        self.subscription_service.activate_subscription(
                            user_id,
                            plan_id,
                            payment_id
                        )
                        logger.info(f"Активирована подписка для пользователя {user_id}, план {plan_id}")

            # Обрабатываем даты правильно
            created_at = payment.created_at
            captured_at = payment.captured_at

            # Преобразуем строковые даты в объекты datetime при необходимости
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    created_at = None

            if isinstance(captured_at, str):
                try:
                    captured_at = datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    captured_at = None

            return {
                "payment_id": payment_id,
                "status": payment.status,
                "paid": payment.paid,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "created_at": created_at.isoformat() if created_at else None,
                "captured_at": captured_at.isoformat() if captured_at else None,
                "description": payment.description
            }

        except Exception as e:
            logger.error(f"Ошибка при проверке статуса платежа: {e}")
            return {"error": "Не удалось проверить статус платежа"}

    def process_webhook_notification(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Обработка уведомления от ЮKassa

        Args:
            payload: Данные уведомления

        Returns:
            Кортеж (успех, сообщение)
        """
        try:
            # Проверяем тип события
            event = payload.get('event')
            if not event:
                return False, "Неизвестный тип события"

            # Получаем данные объекта (платежа)
            payment_data = payload.get('object', {})
            payment_id = payment_data.get('id')

            if not payment_id:
                return False, "ID платежа отсутствует в уведомлении"

            # Получаем метаданные
            metadata = payment_data.get('metadata', {})
            user_id = None
            plan_id = None

            # Проверяем наличие метаданных
            if metadata:
                logger.info(f"Метаданные найдены в уведомлении: {metadata}")
                user_id = int(metadata.get('user_id', 0))
                plan_id = metadata.get('plan_id')

            # Если метаданные отсутствуют или неполные, пытаемся восстановить из БД
            if not user_id or not plan_id:
                logger.warning(
                    f"Метаданные отсутствуют или неполные в уведомлении для платежа {payment_id}. Пробуем восстановить из БД.")
                payment_record = self.session.query(PaymentHistory).filter_by(payment_id=payment_id).first()

                if payment_record:
                    logger.info(
                        f"Найдена запись платежа в БД: ID пользователя={payment_record.user_id}, Тариф={payment_record.plan_id}")
                    user_id = payment_record.user_id
                    plan_id = payment_record.plan_id
                else:
                    logger.error(f"Запись о платеже {payment_id} не найдена в базе данных")
                    return False, "Запись о платеже не найдена в базе данных"

            # Проверяем, что у нас есть необходимые данные
            if not all([user_id, plan_id]):
                logger.error(f"Не удалось восстановить все необходимые данные для платежа {payment_id}")
                return False, "Недостаточно данных для обработки платежа"

            # Получаем запись о платеже или создаем новую
            payment_record = self.session.query(PaymentHistory).filter_by(payment_id=payment_id).first()

            if not payment_record:
                logger.info(f"Создаём новую запись о платеже {payment_id} в БД")
                # Создаем новую запись
                payment_record = PaymentHistory(
                    user_id=user_id,
                    payment_id=payment_id,
                    amount=float(payment_data.get('amount', {}).get('value', 0)),
                    plan_id=plan_id,
                    status=payment_data.get('status', 'pending'),
                    created_at=datetime.utcnow()
                )
                self.session.add(payment_record)

            # Обрабатываем события
            if event == 'payment.succeeded':
                # Платеж успешно завершен
                payment_record.status = 'succeeded'
                payment_record.updated_at = datetime.utcnow()

                # Активируем подписку
                activation_result = self.subscription_service.activate_subscription(
                    user_id,
                    plan_id,
                    payment_id
                )

                if not activation_result:
                    logger.error(f"Ошибка при активации подписки для пользователя {user_id}, тариф {plan_id}")
                    return False, "Ошибка активации подписки"

                message = f"Платеж {payment_id} успешно завершен, тариф {plan_id} активирован для пользователя {user_id}"
                logger.info(message)

            elif event == 'payment.canceled':
                # Платеж отменен
                payment_record.status = 'canceled'
                payment_record.updated_at = datetime.utcnow()
                message = f"Платеж {payment_id} отменен"
                logger.info(message)

            elif event == 'payment.waiting_for_capture':
                # Платеж ожидает подтверждения
                payment_record.status = 'waiting_for_capture'
                payment_record.updated_at = datetime.utcnow()
                message = f"Платеж {payment_id} ожидает подтверждения"
                logger.info(message)

            else:
                # Другие события
                payment_record.status = payment_data.get('status', 'pending')
                payment_record.updated_at = datetime.utcnow()
                message = f"Обработано событие {event} для платежа {payment_id}"
                logger.info(message)

            self.session.commit()
            return True, message

        except Exception as e:
            logger.error(f"Ошибка обработки webhook: {e}", exc_info=True)
            self.session.rollback()
            return False, f"Ошибка обработки уведомления: {str(e)}"

    def refund_payment(
            self,
            payment_id: str,
            amount: Optional[float] = None,
            reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Возврат платежа через ЮKassa

        Args:
            payment_id: ID платежа
            amount: Сумма возврата (если None, возвращается полная сумма)
            reason: Причина возврата

        Returns:
            Словарь с информацией о возврате
        """
        try:
            # Получаем запись о платеже
            payment_record = self.session.query(PaymentHistory).filter_by(payment_id=payment_id).first()

            if not payment_record:
                logger.warning(f"Платеж {payment_id} не найден в базе данных")
                return {"error": "Платеж не найден"}

            # Проверяем статус платежа
            if payment_record.status != 'succeeded':
                return {"error": "Возврат возможен только для успешных платежей"}

            # Если сумма не указана, возвращаем полную сумму
            refund_amount = amount if amount is not None else payment_record.amount

            # Создаем возврат через ЮKassa API
            from yookassa import Refund

            try:
                refund = Refund.create({
                    "payment_id": payment_id,
                    "amount": {
                        "value": str(refund_amount),
                        "currency": PAYMENT_SETTINGS.get('currency', 'RUB')
                    },
                    "description": reason or "Возврат средств"
                })

                logger.info(f"Создан возврат в ЮKassa: {refund.id} для платежа {payment_id}")

                # Обновляем статус платежа
                payment_record.status = 'refunded'
                payment_record.updated_at = datetime.utcnow()
                self.session.commit()

                return {
                    "refund_id": refund.id,
                    "payment_id": payment_id,
                    "amount": refund_amount,
                    "status": refund.status,
                    "created_at": refund.created_at.isoformat() if refund.created_at else None
                }

            except Exception as refund_error:
                logger.error(f"Ошибка при создании возврата в ЮKassa: {refund_error}")
                return {"error": f"Ошибка создания возврата: {str(refund_error)}"}

        except Exception as e:
            logger.error(f"Ошибка при создании возврата: {e}")
            self.session.rollback()
            return {"error": "Внутренняя ошибка создания возврата"}

    def get_payment_history(
            self,
            user_id: int
    ) -> Dict[str, Any]:
        """
        Получение истории платежей с учетом конфиденциальности

        Args:
            user_id: ID пользователя

        Returns:
            Словарь с историей платежей
        """
        try:
            # Получаем pseudonym_id
            pseudonym_id = self.encryption_service.ensure_pseudonym(user_id)

            # Получаем историю платежей
            payments = self.session.query(PaymentHistory) \
                .filter(PaymentHistory.user_id == user_id) \
                .order_by(PaymentHistory.created_at.desc()) \
                .limit(10) \
                .all()

            return {
                'pseudonym_id': pseudonym_id,
                'payments': [
                    {
                        'payment_id': payment.payment_id,
                        'plan_id': payment.plan_id,
                        'amount': payment.amount,
                        'status': payment.status,
                        'created_at': payment.created_at.isoformat() if payment.created_at else None,
                        'updated_at': payment.updated_at.isoformat() if payment.updated_at else None
                    }
                    for payment in payments
                ]
            }

        except Exception as e:
            logger.error(f"Ошибка получения истории платежей: {e}")
            return {
                'pseudonym_id': None,
                'payments': []
            }

    def verify_webhook_signature(self, data: bytes, signature: str) -> bool:
        """
        Проверка подписи webhook от ЮKassa

        Args:
            data: Сырые данные запроса
            signature: Подпись из заголовка X-YooKassa-Signature

        Returns:
            Результат проверки подписи
        """
        try:
            import hmac
            import hashlib
            import base64

            secret_key = YOOKASSA_SECRET_KEY.encode('utf-8')

            hmac_obj = hmac.new(secret_key, data, hashlib.sha256)
            calculated_signature = base64.b64encode(hmac_obj.digest()).decode('utf-8')

            return hmac.compare_digest(signature, calculated_signature)

        except Exception as e:
            logger.error(f"Ошибка проверки подписи webhook: {e}")
            return False
