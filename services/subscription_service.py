# services/subscription_service_sync.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from database.models import (
    UserCredits,
    UserSubscription,
    UserPseudonym,
    PaymentHistory
)
from config.settings import (
    ANONYMIZATION_SETTINGS,
    PRICING_PLANS,
    CREDIT_SETTINGS,
    PAYMENT_SETTINGS
)
from services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    Синхронная версия сервиса для управления подписками и кредитами
    """

    def __init__(
            self,
            session: Session,
            encryption_service: Optional[EncryptionService] = None
    ):
        """
        Инициализация сервиса подписок

        Args:
            session: Сессия SQLAlchemy
            encryption_service: Сервис шифрования (создается при необходимости)
        """
        self.session = session
        self.encryption_service = encryption_service or EncryptionService(session)

        # Настройки конфиденциальности
        self.pseudonymize = ANONYMIZATION_SETTINGS.get(
            'enable_pseudonymization',
            True
        )

    def activate_subscription(
            self,
            user_id: int,
            plan_id: str,
            payment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Активация подписки с учетом конфиденциальности
        """
        try:
            # Получаем pseudonym_id
            pseudonym_id = self.encryption_service.ensure_pseudonym(user_id)

            # Проверяем существование плана
            plan = PRICING_PLANS.get(plan_id)
            if not plan:
                logger.warning(f"Invalid plan_id: {plan_id}")
                return {}

            # Деактивируем текущую подписку
            self._deactivate_current_subscription(user_id)

            # Создаем новую подписку
            subscription = UserSubscription(
                user_id=user_id,
                plan_id=plan_id,
                status='active',
                start_date=datetime.utcnow(),
                end_date=None  # Бессрочная подписка
            )
            self.session.add(subscription)

            # Обновляем кредиты
            self._update_user_credits(user_id, plan_id)

            # Сохраняем информацию о платеже, если ID платежа предоставлен
            # и такой платеж еще не существует
            if payment_id:
                existing_payment = self.session.query(PaymentHistory).filter_by(payment_id=payment_id).first()
                if not existing_payment:
                    payment_record = PaymentHistory(
                        user_id=user_id,
                        payment_id=payment_id,
                        amount=float(plan.get('price', 0)),
                        plan_id=plan_id,
                        status='succeeded',
                        created_at=datetime.utcnow()
                    )
                    self.session.add(payment_record)
                else:
                    # Обновляем статус существующего платежа, если он не 'succeeded'
                    if existing_payment.status != 'succeeded':
                        existing_payment.status = 'succeeded'
                        existing_payment.updated_at = datetime.utcnow()

            self.session.commit()

            return {
                'pseudonym_id': pseudonym_id,
                'plan_id': plan_id,
                'status': 'active',
                'start_date': subscription.start_date.isoformat()
            }

        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            self.session.rollback()
            return {}

    def _deactivate_current_subscription(self, user_id: int) -> bool:
        """
        Деактивация текущей подписки пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Успешность деактивации
        """
        try:
            # Находим активную подписку
            active_sub = self.session.query(UserSubscription) \
                .filter(
                UserSubscription.user_id == user_id,
                UserSubscription.status == 'active'
            ).first()

            if active_sub:
                active_sub.status = 'cancelled'
                active_sub.end_date = datetime.utcnow()

            return True

        except Exception as e:
            logger.error(f"Error deactivating subscription: {e}")
            return False

    def _update_user_credits(
            self,
            user_id: int,
            plan_id: str,
            payment_id: Optional[str] = None
    ):
        """
        Обновление кредитов пользователя

        Args:
            user_id: ID пользователя
            plan_id: Идентификатор тарифного плана
            payment_id: ID платежа (опционально)
        """
        try:
            # Получаем количество кредитов для плана
            plan = PRICING_PLANS.get(plan_id, {})
            credits = plan.get('messages', 0)

            # Находим или создаем запись о кредитах
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            if user_credits:
                # Увеличиваем кредиты
                user_credits.credits_remaining += credits
                user_credits.last_purchase_date = datetime.utcnow()

                # Отмечаем использование пробного периода
                if plan_id == 'trial':
                    user_credits.has_used_trial = True
            else:
                # Создаем новую запись о кредитах
                user_credits = UserCredits(
                    user_id=user_id,
                    credits_remaining=credits,
                    has_used_trial=plan_id == 'trial',
                    last_purchase_date=datetime.utcnow()
                )
                self.session.add(user_credits)

            logger.info(f"Updated credits for user {user_id}: +{credits} credits, plan: {plan_id}")

        except Exception as e:
            logger.error(f"Error updating user credits: {e}")
            raise

    def get_user_subscription_status(
            self,
            user_id: int
    ) -> Dict[str, Any]:
        """
        Получение статуса подписки пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Словарь со статусом подписки и кредитов
        """
        try:
            # Получаем pseudonym_id
            pseudonym_id = self.encryption_service.ensure_pseudonym(user_id)

            # Находим активную подписку
            active_sub = self.session.query(UserSubscription) \
                .filter(
                UserSubscription.user_id == user_id,
                UserSubscription.status == 'active'
            ).first()

            # Находим информацию о кредитах
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            return {
                'pseudonym_id': pseudonym_id,
                'has_active_subscription': bool(active_sub),
                'plan_id': active_sub.plan_id if active_sub else None,
                'credits_remaining': user_credits.credits_remaining if user_credits else 0,
                'subscription_start': active_sub.start_date.isoformat() if active_sub else None,
                'subscription_end': active_sub.end_date.isoformat() if active_sub and active_sub.end_date else None,
                'has_used_trial': user_credits.has_used_trial if user_credits else False
            }

        except Exception as e:
            logger.error(f"Error getting subscription status: {e}")
            return {
                'pseudonym_id': None,
                'has_active_subscription': False,
                'plan_id': None,
                'credits_remaining': 0,
                'subscription_start': None,
                'subscription_end': None,
                'has_used_trial': False
            }

    def get_subscription_history(
            self,
            user_id: int
    ) -> Dict[str, Any]:
        """
        Получение истории подписок пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Словарь с историей подписок
        """
        try:
            # Получаем pseudonym_id
            pseudonym_id = self.encryption_service.ensure_pseudonym(user_id)

            # Получаем историю подписок
            subscriptions = self.session.query(UserSubscription) \
                .filter(UserSubscription.user_id == user_id) \
                .order_by(UserSubscription.created_at.desc()) \
                .all()

            # Получаем историю платежей
            payments = self.session.query(PaymentHistory) \
                .filter(PaymentHistory.user_id == user_id) \
                .order_by(PaymentHistory.created_at.desc()) \
                .all()

            return {
                'pseudonym_id': pseudonym_id,
                'subscriptions': [
                    {
                        'plan_id': sub.plan_id,
                        'status': sub.status,
                        'start_date': sub.start_date.isoformat(),
                        'end_date': sub.end_date.isoformat() if sub.end_date else None,
                        'created_at': sub.created_at.isoformat()
                    }
                    for sub in subscriptions
                ],
                'payments': [
                    {
                        'payment_id': payment.payment_id,
                        'plan_id': payment.plan_id,
                        'amount': payment.amount,
                        'status': payment.status,
                        'created_at': payment.created_at.isoformat()
                    }
                    for payment in payments
                ]
            }

        except Exception as e:
            logger.error(f"Error getting subscription history: {e}")
            return {
                'pseudonym_id': None,
                'subscriptions': [],
                'payments': []
            }

    def use_credit(
            self,
            user_id: int,
            credit_cost: int = 1
    ) -> bool:
        """
        Списание кредитов с учетом конфиденциальности

        Args:
            user_id: ID пользователя
            credit_cost: Стоимость операции в кредитах

        Returns:
            Успешность списания кредитов
        """
        try:
            # Находим запись о кредитах
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            if not user_credits or user_credits.credits_remaining < credit_cost:
                return False

            # Списываем кредиты
            user_credits.credits_remaining -= credit_cost
            self.session.commit()

            return True

        except Exception as e:
            logger.error(f"Error using credits: {e}")
            self.session.rollback()
            return False

    def can_use_service(self, user_id: int) -> bool:
        """
        Проверка возможности использования сервиса

        Args:
            user_id: ID пользователя

        Returns:
            Возможность использования сервиса
        """
        try:
            # Находим запись о кредитах
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            return bool(user_credits and user_credits.credits_remaining > 0)

        except Exception as e:
            logger.error(f"Error checking service availability: {e}")
            return False
