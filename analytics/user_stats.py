import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from database.models import UserAction

logger = logging.getLogger(__name__)

def get_user_stats(session: Session, start_date: datetime, end_date: datetime):
    """Получение статистики по пользователям"""
    try:
        return {
            'total_unique': _count_unique_users(session, start_date, end_date),
            'new_users': _count_new_users(session, start_date, end_date),
            'returning_users': _count_returning_users(session, start_date, end_date),
            'active_users': _count_active_users(session, start_date, end_date)
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {
            'total_unique': 0,
            'new_users': 0,
            'returning_users': 0,
            'active_users': 0
        }

def _count_unique_users(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет уникальных пользователей за период"""
    return session.query(func.count(distinct(UserAction.user_id))) \
        .filter(UserAction.created_at.between(start_date, end_date)) \
        .scalar() or 0

def _count_new_users(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет новых пользователей"""
    first_actions = session.query(
        UserAction.user_id,
        func.min(UserAction.created_at).label('first_action')
    ).group_by(UserAction.user_id).subquery()

    return session.query(first_actions) \
        .filter(first_actions.c.first_action.between(start_date, end_date)) \
        .count()

def _count_returning_users(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет вернувшихся пользователей"""
    previous_users = session.query(distinct(UserAction.user_id)) \
        .filter(UserAction.created_at < start_date) \
        .subquery()

    return session.query(distinct(UserAction.user_id)) \
        .filter(
            UserAction.user_id.in_(previous_users),
            UserAction.created_at.between(start_date, end_date)
        ).count()

def _count_active_users(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет активных пользователей (минимум 3 действия)"""
    return session.query(UserAction.user_id) \
        .filter(UserAction.created_at.between(start_date, end_date)) \
        .group_by(UserAction.user_id) \
        .having(func.count(UserAction.id) >= 3) \
        .count()
