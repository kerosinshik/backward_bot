# services/analytics_service.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from sqlalchemy.exc import SQLAlchemyError

from database.models import UserAction, UserPseudonym
from analytics.user_stats import get_user_stats
from analytics.engagement_stats import get_engagement_stats
from analytics.consultation_stats import get_consultation_analytics
from analytics.error_stats import get_error_stats

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Сервис для анализа статистики пользователей и использования бота"""

    def __init__(self, session: Session):
        """
        Инициализация сервиса аналитики

        Args:
            session: Сессия SQLAlchemy для работы с базой данных
        """
        self.session = session  # Сохраняем сессию как атрибут класса

    def get_daily_stats(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Получение статистики за день

        Args:
            date: Дата для анализа (по умолчанию сегодня)

        Returns:
            Dict[str, Any]: Словарь со статистикой
        """
        # Создаем локальную сессию для изоляции ошибок
        local_session = self.session

        try:
            # Настраиваем временные рамки
            if not date:
                date = datetime.utcnow()

            start_date = datetime(date.year, date.month, date.day, 0, 0, 0)
            end_date = start_date + timedelta(days=1)

            # Создаем пустой базовый результат на случай сбоя отдельных компонентов
            result = self._get_empty_stats(date)

            # Получаем статистику из разных модулей с защитой от ошибок
            try:
                result['users'] = get_user_stats(local_session, start_date, end_date)
            except Exception as user_e:
                logger.error(f"Error getting user stats: {user_e}")
                # Оставляем пустые значения по умолчанию для этой секции

            try:
                result['engagement'] = get_engagement_stats(local_session, start_date, end_date)
            except Exception as engagement_e:
                logger.error(f"Error getting engagement stats: {engagement_e}")
                # Оставляем пустые значения по умолчанию для этой секции

            try:
                result['consultations'] = get_consultation_analytics(local_session, start_date, end_date)
            except Exception as consultation_e:
                logger.error(f"Error getting consultation stats: {consultation_e}")
                # Оставляем пустые значения по умолчанию для этой секции

            try:
                result['errors'] = get_error_stats(local_session, start_date, end_date)
            except Exception as error_e:
                logger.error(f"Error getting error stats: {error_e}")
                # Оставляем пустые значения по умолчанию для этой секции

            # Добавляем дату
            result['date'] = date.strftime('%Y-%m-%d')

            return result

        except Exception as e:
            logger.error(f"Error in get_daily_stats: {e}", exc_info=True)
            return self._get_empty_stats(date)

    def log_action(self, user_id: int, action_type: str, content: Optional[str] = None) -> bool:
        """
        Логирование действия пользователя

        Args:
            user_id: ID пользователя
            action_type: Тип действия
            content: Содержимое действия (опционально)

        Returns:
            bool: Успешность операции
        """
        try:
            new_action = UserAction(
                user_id=user_id,
                action_type=action_type,
                content=content,
                created_at=datetime.utcnow()
            )

            self.session.add(new_action)
            self.session.commit()

            return True
        except SQLAlchemyError as db_error:
            logger.error(f"Database error in log_action: {db_error}")
            self.session.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error in log_action: {e}", exc_info=True)
            self.session.rollback()
            return False

    def log_first_time_user(self, user_id: int) -> bool:
        """
        Логирование первого использования ботом

        Args:
            user_id: ID пользователя

        Returns:
            bool: Является ли пользователь новым
        """
        try:
            # Проверяем, есть ли у пользователя предыдущие действия
            existing_actions = self.session.query(UserAction) \
                .filter(UserAction.user_id == user_id) \
                .first()

            if existing_actions:
                return False

            # Если это первое действие, логируем его
            new_action = UserAction(
                user_id=user_id,
                action_type='first_use',
                created_at=datetime.utcnow()
            )

            self.session.add(new_action)
            self.session.commit()

            return True
        except SQLAlchemyError as db_error:
            logger.error(f"Database error in log_first_time_user: {db_error}")
            self.session.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error in log_first_time_user: {e}", exc_info=True)
            self.session.rollback()
            return False

    def _get_empty_stats(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Создание пустой структуры статистики

        Args:
            date: Дата для статистики

        Returns:
            Dict[str, Any]: Пустая структура статистики
        """
        date_str = date.strftime('%Y-%m-%d') if date else datetime.utcnow().strftime('%Y-%m-%d')

        return {
            'date': date_str,
            'users': {
                'total_unique': 0,
                'new_users': 0,
                'returning_users': 0,
                'active_users': 0
            },
            'engagement': {
                'total_actions': 0,
                'command_usage': {},
                'peak_hours': {},
                'daily_engagement': {}
            },
            'consultations': {
                'total_consultations': 0,
                'consultation_length': {},
                'topic_distribution': {}
            },
            'errors': {
                'total_errors': 0,
                'error_rate': 0,
                'error_types': {}
            }
        }
