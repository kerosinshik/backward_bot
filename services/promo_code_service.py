# services/promo_code_service.py
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from database.models import (
    PromoCode,
    PromoCodeUsage,
    UserCredits,
    UserPseudonym
)

logger = logging.getLogger(__name__)


class PromoCodeService:
    """
    Сервис для работы с промокодами (синхронная реализация)
    """

    def __init__(self, session: Session):
        """
        Инициализация сервиса промокодов

        Args:
            session: Сессия SQLAlchemy
        """
        self.session = session

    def create_promo_code(
            self,
            code: str,
            credits: int,
            max_uses: Optional[int] = None,
            created_by: Optional[int] = None,
            expires_at: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Создание нового промокода

        Args:
            code: Код промокода
            credits: Количество кредитов
            max_uses: Максимальное количество использований (опционально)
            created_by: ID создателя (администратора)
            expires_at: Дата истечения срока действия (опционально)

        Returns:
            Кортеж (успех, сообщение)
        """
        try:
            # Проверяем, существует ли промокод с таким кодом
            existing_promo = self.session.query(PromoCode).filter_by(code=code).first()

            if existing_promo:
                return False, f"Промокод '{code}' уже существует"

            # Создаем новый промокод
            promo_code = PromoCode(
                code=code,
                credits=credits,
                max_uses=max_uses,
                created_by=created_by,
                expires_at=expires_at,
                is_active=True,
                used_count=0,
                created_at=datetime.utcnow()
            )

            self.session.add(promo_code)
            self.session.commit()

            return True, f"Промокод '{code}' успешно создан"

        except Exception as e:
            logger.error(f"Error creating promo code: {e}")
            self.session.rollback()
            return False, f"Ошибка при создании промокода: {str(e)}"

    def activate_promo_code(self, user_id: int, code: str) -> Tuple[bool, str, int]:
        """
        Активация промокода пользователем

        Args:
            user_id: ID пользователя
            code: Код промокода

        Returns:
            Кортеж (успех, сообщение, количество кредитов)
        """
        try:
            # Проверяем, существует ли промокод
            promo_code = self.session.query(PromoCode).filter_by(code=code).first()

            if not promo_code:
                return False, "Промокод не найден", 0

            # Проверяем, активен ли промокод
            if not promo_code.is_active:
                return False, "Промокод неактивен", 0

            # Проверяем, не истек ли срок действия
            if promo_code.expires_at and promo_code.expires_at < datetime.utcnow():
                return False, "Срок действия промокода истек", 0

            # Проверяем, не превышено ли максимальное количество использований
            if promo_code.max_uses and promo_code.used_count >= promo_code.max_uses:
                return False, "Промокод больше не доступен (достигнут лимит использований)", 0

            # Проверяем, не использовал ли пользователь этот промокод ранее
            usage = self.session.query(PromoCodeUsage).filter_by(
                user_id=user_id,
                promo_code=code
            ).first()

            if usage:
                return False, "Вы уже использовали этот промокод", 0

            # Обновляем счетчик использований
            promo_code.used_count += 1

            # Создаем запись об использовании
            usage = PromoCodeUsage(
                user_id=user_id,
                promo_code=code,
                credits_granted=promo_code.credits,
                activated_at=datetime.utcnow()
            )
            self.session.add(usage)

            # Начисляем кредиты пользователю
            user_credits = self.session.query(UserCredits).filter_by(user_id=user_id).first()

            if user_credits:
                user_credits.credits_remaining += promo_code.credits
            else:
                user_credits = UserCredits(
                    user_id=user_id,
                    credits_remaining=promo_code.credits,
                    has_used_trial=False,
                    last_purchase_date=datetime.utcnow()
                )
                self.session.add(user_credits)

            # Деактивируем промокод, если достигнут лимит использований
            if promo_code.max_uses and promo_code.used_count >= promo_code.max_uses:
                promo_code.is_active = False

            self.session.commit()

            return True, f"Промокод активирован! Вам начислено {promo_code.credits} кредитов", promo_code.credits

        except Exception as e:
            logger.error(f"Error activating promo code: {e}")
            self.session.rollback()
            return False, f"Ошибка при активации промокода: {str(e)}", 0

    def disable_promo_code(self, code: str, admin_id: int) -> Tuple[bool, str]:
        """
        Деактивация промокода администратором

        Args:
            code: Код промокода
            admin_id: ID администратора

        Returns:
            Кортеж (успех, сообщение)
        """
        try:
            # Проверяем, существует ли промокод
            promo_code = self.session.query(PromoCode).filter_by(code=code).first()

            if not promo_code:
                return False, "Промокод не найден"

            # Деактивируем промокод
            promo_code.is_active = False
            self.session.commit()

            return True, f"Промокод '{code}' успешно деактивирован"

        except Exception as e:
            logger.error(f"Error disabling promo code: {e}")
            self.session.rollback()
            return False, f"Ошибка при деактивации промокода: {str(e)}"

    def get_promo_code_stats(self, code: Optional[str] = None) -> Dict[str, Any]:
        """
        Получение статистики по промокодам

        Args:
            code: Код конкретного промокода (опционально)

        Returns:
            Статистика по промокодам
        """
        try:
            stats = {
                'total_codes': 0,
                'active_codes': 0,
                'total_usages': 0,
                'total_credits_granted': 0,
                'promo_codes': []
            }

            # Если указан конкретный промокод
            if code:
                promo_code = self.session.query(PromoCode).filter_by(code=code).first()

                if not promo_code:
                    return stats

                # Получаем статистику использования
                usages = self.session.query(PromoCodeUsage).filter_by(promo_code=code).all()
                total_credits = sum(usage.credits_granted for usage in usages)

                stats['promo_codes'] = [{
                    'code': promo_code.code,
                    'credits': promo_code.credits,
                    'is_active': promo_code.is_active,
                    'max_uses': promo_code.max_uses,
                    'used_count': promo_code.used_count,
                    'created_at': promo_code.created_at.isoformat(),
                    'expires_at': promo_code.expires_at.isoformat() if promo_code.expires_at else None,
                    'total_credits_granted': total_credits,
                    'unique_users': len(usages)
                }]

                stats['total_codes'] = 1
                stats['active_codes'] = 1 if promo_code.is_active else 0
                stats['total_usages'] = promo_code.used_count
                stats['total_credits_granted'] = total_credits

                return stats

            # Получаем общую статистику
            promo_codes = self.session.query(PromoCode).all()
            active_codes = sum(1 for p in promo_codes if p.is_active)
            total_usages = sum(p.used_count for p in promo_codes)

            # Получаем сумму всех начисленных кредитов
            total_credits = self.session.query(func.sum(PromoCodeUsage.credits_granted)).scalar() or 0

            # Собираем информацию по каждому промокоду
            promo_stats = []
            for promo in promo_codes:
                usages = self.session.query(PromoCodeUsage).filter_by(promo_code=promo.code).all()
                promo_stats.append({
                    'code': promo.code,
                    'credits': promo.credits,
                    'is_active': promo.is_active,
                    'max_uses': promo.max_uses,
                    'used_count': promo.used_count,
                    'created_at': promo.created_at.isoformat(),
                    'expires_at': promo.expires_at.isoformat() if promo.expires_at else None,
                    'total_credits_granted': sum(usage.credits_granted for usage in usages),
                    'unique_users': len(usages)
                })

            stats['total_codes'] = len(promo_codes)
            stats['active_codes'] = active_codes
            stats['total_usages'] = total_usages
            stats['total_credits_granted'] = total_credits
            stats['promo_codes'] = promo_stats

            return stats

        except Exception as e:
            logger.error(f"Error getting promo code stats: {e}")
            return {
                'total_codes': 0,
                'active_codes': 0,
                'total_usages': 0,
                'total_credits_granted': 0,
                'promo_codes': [],
                'error': str(e)
            }
