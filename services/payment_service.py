# services/payment_service.py

import logging
from datetime import datetime, timedelta, time
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

from yookassa import Configuration, Payment
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from backward_bot.database.models import UserCredits, PaymentHistory, UserSubscription
from backward_bot.config.settings import (
    YOOKASSA_SHOP_ID,
    YOOKASSA_SECRET_KEY,
    BOT_USERNAME,
    PAYMENT_RETURN_URL,
    PRICING_PLANS
)

logger = logging.getLogger(__name__)


class PaymentService:
    """Сервис для работы с платежами и подписками"""

    def __init__(self, session: Session):
        """
        Инициализация сервиса платежей

        Args:
            session: Сессия SQLAlchemy для работы с БД
        """
        self.session = session
        # Инициализация ЮKassa
        Configuration.account_id = YOOKASSA_SHOP_ID
        Configuration.secret_key = YOOKASSA_SECRET_KEY

    async def create_payment(self, user_id: int, plan_id: str, amount: float,
                             description: str) -> Dict[str, Any]:
        """
        Создает новый платеж в ЮKassa

        Args:
            user_id: ID пользователя в Telegram
            plan_id: Идентификатор тарифного плана
            amount: Сумма платежа
            description: Описание платежа

        Returns:
            Dict с данными платежа, включая URL для оплаты
        """
        try:
            # Подготовка метаданных платежа
            metadata = {
                'user_id': str(user_id),
                'plan_id': plan_id,
                'bot_username': BOT_USERNAME
            }

            # Формирование параметров для возврата
            return_url = PAYMENT_RETURN_URL + '?' + urlencode({
                'user_id': user_id,
                'plan_id': plan_id
            })

            # Создание платежа в ЮKassa
            payment = Payment.create({
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": description,
                "metadata": metadata,
                "receipt": {
                    "customer": {
                        "email": f"{user_id}@telegram.bot"  # Временный email для чека
                    },
                    "items": [
                        {
                            "description": description,
                            "quantity": "1.00",
                            "amount": {
                                "value": str(amount),
                                "currency": "RUB"
                            },
                            "vat_code": "1",
                            "payment_mode": "full_prepayment",
                            "payment_subject": "service"
                        }
                    ]
                }
            })

            # Сохраняем информацию о платеже в БД
            payment_history = PaymentHistory(
                user_id=user_id,
                payment_id=payment.id,
                amount=amount,
                plan_id=plan_id,
                status='pending',
                created_at=datetime.utcnow()
            )
            self.session.add(payment_history)
            self.session.commit()

            return {
                'payment_id': payment.id,
                'confirmation_url': payment.confirmation.confirmation_url,
                'status': payment.status
            }

        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            self.session.rollback()
            raise

    async def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Проверяет статус платежа в ЮKassa

        Args:
            payment_id: ID платежа в ЮKassa

        Returns:
            Dict с информацией о статусе платежа
        """
        try:
            payment = Payment.find_one(payment_id)
            return {
                'status': payment.status,
                'paid': payment.paid,
                'amount': float(payment.amount.value),
                'metadata': payment.metadata
            }
        except Exception as e:
            logger.error(f"Error checking payment status: {e}")
            raise

    async def process_successful_payment(self, payment_id: str) -> bool:
        """
        Обрабатывает успешный платеж

        Args:
            payment_id: ID платежа в ЮKassa

        Returns:
            bool: Успешность обработки платежа
        """
        try:
            # Получаем информацию о платеже из нашей БД
            payment_history = self.session.query(PaymentHistory) \
                .filter_by(payment_id=payment_id) \
                .first()

            if not payment_history:
                logger.error(f"Payment {payment_id} not found in database")
                return False

            if payment_history.status == 'succeeded':
                logger.info(f"Payment {payment_id} already processed")
                return True

            # Обновляем статус платежа
            payment_history.status = 'succeeded'
            payment_history.updated_at = datetime.utcnow()

            # Активируем подписку или добавляем кредиты
            await self._activate_plan(
                user_id=payment_history.user_id,
                plan_id=payment_history.plan_id
            )

            self.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error processing successful payment: {e}")
            self.session.rollback()
            return False

    async def _activate_plan(self, user_id: int, plan_id: str):
        """
        Активирует тарифный план для пользователя

        Args:
            user_id: ID пользователя
            plan_id: Идентификатор плана
        """
        plan_credits = {
            'trial': 20,
            'basic': 100,
            'standard': 300
        }

        credits = plan_credits.get(plan_id, 0)
        if not credits:
            raise ValueError(f"Invalid plan_id: {plan_id}")

        user_credits = self.session.query(UserCredits) \
            .filter_by(user_id=user_id) \
            .first()

        if user_credits:
            user_credits.credits_remaining += credits
            user_credits.last_purchase_date = datetime.utcnow()
        else:
            user_credits = UserCredits(
                user_id=user_id,
                credits_remaining=credits,
                last_purchase_date=datetime.utcnow()
            )
            self.session.add(user_credits)

    async def get_user_credits(self, user_id: int) -> Optional[int]:
        """
        Получает количество доступных кредитов пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Optional[int]: Количество доступных кредитов или None
        """
        try:
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()
            return user_credits.credits_remaining if user_credits else None
        except Exception as e:
            logger.error(f"Error getting user credits: {e}")
            return None

    async def use_credit(self, user_id: int, amount: int = 1) -> bool:
        """
        Использует кредиты пользователя

        Args:
            user_id: ID пользователя
            amount: Количество кредитов для списания

        Returns:
            bool: Успешность операции
        """
        try:
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            if not user_credits or user_credits.credits_remaining < amount:
                return False

            user_credits.credits_remaining -= amount
            self.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error using credits: {e}")
            self.session.rollback()
            return False

    async def get_payment_history(self, user_id: int,
                                  limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает историю платежей пользователя

        Args:
            user_id: ID пользователя
            limit: Максимальное количество записей

        Returns:
            List[Dict]: История платежей
        """
        try:
            payments = self.session.query(PaymentHistory) \
                .filter_by(user_id=user_id) \
                .order_by(PaymentHistory.created_at.desc()) \
                .limit(limit) \
                .all()

            return [{
                'payment_id': p.payment_id,
                'amount': p.amount,
                'plan_id': p.plan_id,
                'status': p.status,
                'created_at': p.created_at.isoformat(),
                'updated_at': p.updated_at.isoformat() if p.updated_at else None
            } for p in payments]

        except Exception as e:
            logger.error(f"Error getting payment history: {e}")
            return []


class DemoPaymentService:
    """Демо-сервис для эмуляции платежей"""

    async def create_payment(self, user_id: int, plan_id: str, amount: float, description: str):
        """Эмулирует создание платежа"""
        payment_id = f"demo_{user_id}_{int(time.time())}"
        return {
            'payment_id': payment_id,
            'confirmation_url': '#demo_payment',
            'status': 'pending'
        }

    async def check_payment_status(self, payment_id: str):
        """Всегда возвращает успешный статус в демо-режиме"""
        return {
            'status': 'succeeded',
            'paid': True,
            'amount': 0,
            'metadata': {}
        }

    async def activate_demo_plan(self, user_id: int, plan_id: str) -> bool:
        """Активация демо-тарифа"""
        try:
            plan = PRICING_PLANS.get(plan_id)
            if not plan:
                return False

            # Активируем кредиты
            credits = plan['messages']
            user_credits = self.session.query(UserCredits).filter_by(user_id=user_id).first()

            if user_credits:
                user_credits.credits_remaining += credits
            else:
                user_credits = UserCredits(
                    user_id=user_id,
                    credits_remaining=credits,
                    last_purchase_date=datetime.utcnow()
                )
                self.session.add(user_credits)

            # Создаем запись о демо-подписке
            demo_subscription = UserSubscription(
                user_id=user_id,
                plan_id=plan_id,
                status='active',
                start_date=datetime.utcnow(),
                end_date=None
            )
            self.session.add(demo_subscription)

            self.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error in demo plan activation: {e}")
            self.session.rollback()
            return False
