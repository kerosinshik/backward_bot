# services/subscription_service.py

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database.models import UserSubscription, UserCredits
from config.settings import PRICING_PLANS

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Сервис для управления подписками пользователей"""

    def __init__(self, session: Session):
        """
        Инициализация сервиса подписок

        Args:
            session: Сессия SQLAlchemy для работы с БД
        """
        self.session = session

    async def get_active_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """
        Получает активную подписку пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Optional[UserSubscription]: Активная подписка или None
        """
        try:
            now = datetime.utcnow()
            return self.session.query(UserSubscription).filter(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status == 'active',
                    UserSubscription.start_date <= now,
                    or_(
                        UserSubscription.end_date.is_(None),
                        UserSubscription.end_date > now
                    )
                )
            ).first()
        except Exception as e:
            logger.error(f"Error getting active subscription: {e}")
            return None

    async def activate_subscription(self, user_id: int, plan_id: str) -> bool:
        """
        Активирует подписку для пользователя

        Args:
            user_id: ID пользователя
            plan_id: Идентификатор тарифного плана

        Returns:
            bool: Успешность активации
        """
        try:
            # Проверяем существование плана
            if plan_id not in PRICING_PLANS:
                logger.error(f"Invalid plan_id: {plan_id}")
                return False

            # Деактивируем текущую активную подписку, если есть
            await self.deactivate_current_subscription(user_id)

            # Создаем новую подписку
            subscription = UserSubscription(
                user_id=user_id,
                plan_id=plan_id,
                status='active',
                start_date=datetime.utcnow(),
                end_date=None  # Бессрочная подписка
            )

            self.session.add(subscription)

            # Добавляем кредиты согласно плану
            await self._add_plan_credits(user_id, plan_id)

            self.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            self.session.rollback()
            return False

    async def deactivate_current_subscription(self, user_id: int) -> bool:
        """
        Деактивирует текущую подписку пользователя

        Args:
            user_id: ID пользователя

        Returns:
            bool: Успешность деактивации
        """
        try:
            active_sub = await self.get_active_subscription(user_id)
            if active_sub:
                active_sub.status = 'cancelled'
                active_sub.end_date = datetime.utcnow()
                self.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error deactivating subscription: {e}")
            self.session.rollback()
            return False

    async def _add_plan_credits(self, user_id: int, plan_id: str):
        """
        Добавляет кредиты согласно выбранному плану

        Args:
            user_id: ID пользователя
            plan_id: Идентификатор плана
        """
        try:
            plan = PRICING_PLANS.get(plan_id)
            if not plan:
                return

            credits = plan.get('messages', 0)
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            if user_credits:
                user_credits.credits_remaining += credits
            else:
                user_credits = UserCredits(
                    user_id=user_id,
                    credits_remaining=credits,
                    last_purchase_date=datetime.utcnow()
                )
                self.session.add(user_credits)

        except Exception as e:
            logger.error(f"Error adding plan credits: {e}")
            raise

    async def get_subscription_history(self, user_id: int) -> List[Dict]:
        """
        Получает историю подписок пользователя

        Args:
            user_id: ID пользователя

        Returns:
            List[Dict]: История подписок
        """
        try:
            subscriptions = self.session.query(UserSubscription) \
                .filter_by(user_id=user_id) \
                .order_by(UserSubscription.created_at.desc()) \
                .all()

            return [{
                'plan_id': sub.plan_id,
                'status': sub.status,
                'start_date': sub.start_date.isoformat(),
                'end_date': sub.end_date.isoformat() if sub.end_date else None,
                'created_at': sub.created_at.isoformat()
            } for sub in subscriptions]

        except Exception as e:
            logger.error(f"Error getting subscription history: {e}")
            return []

    async def check_subscription_status(self, user_id: int) -> Dict:
        """
        Проверяет статус подписки пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Dict: Информация о статусе подписки
        """
        try:
            active_sub = await self.get_active_subscription(user_id)
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            return {
                'has_active_subscription': bool(active_sub),
                'plan_id': active_sub.plan_id if active_sub else None,
                'credits_remaining': user_credits.credits_remaining if user_credits else 0,
                'subscription_start': active_sub.start_date.isoformat() if active_sub else None,
                'subscription_end': active_sub.end_date.isoformat() if active_sub and active_sub.end_date else None
            }

        except Exception as e:
            logger.error(f"Error checking subscription status: {e}")
            return {
                'has_active_subscription': False,
                'plan_id': None,
                'credits_remaining': 0,
                'subscription_start': None,
                'subscription_end': None
            }

    async def can_use_service(self, user_id: int) -> bool:
        """
        Проверяет, может ли пользователь использовать сервис

        Args:
            user_id: ID пользователя

        Returns:
            bool: Доступность сервиса
        """
        try:
            user_credits = self.session.query(UserCredits) \
                .filter_by(user_id=user_id) \
                .first()

            return bool(user_credits and user_credits.credits_remaining > 0)

        except Exception as e:
            logger.error(f"Error checking service availability: {e}")
            return False
