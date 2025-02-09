import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from database.models import UserAction

logger = logging.getLogger(__name__)


def get_error_stats(session: Session, start_date: datetime, end_date: datetime):
    """Получение статистики по ошибкам"""
    try:
        total_errors = _count_total_errors(session, start_date, end_date)
        total_actions = _count_total_actions(session, start_date, end_date)

        return {
            'total_errors': total_errors,
            'error_rate': (total_errors / total_actions * 100) if total_actions > 0 else 0,
            'error_types': _get_error_types(session, start_date, end_date),
            'error_users': _get_users_with_errors(session, start_date, end_date)
        }
    except Exception as e:
        logger.error(f"Error getting error stats: {e}")
        return {
            'total_errors': 0,
            'error_rate': 0,
            'error_types': {},
            'error_users': []
        }


def _count_total_errors(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет общего количества ошибок"""
    return session.query(func.count(UserAction.id)) \
        .filter(
        UserAction.action_type == 'error',
        UserAction.created_at.between(start_date, end_date)
    ).scalar() or 0


def _count_total_actions(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет общего количества действий"""
    return session.query(func.count(UserAction.id)) \
        .filter(
        UserAction.created_at.between(start_date, end_date)
    ).scalar() or 0


def _get_error_types(session: Session, start_date: datetime, end_date: datetime):
    """Получение статистики по типам ошибок"""
    error_types = session.query(
        UserAction.content,
        func.count(UserAction.id)
    ).filter(
        UserAction.action_type == 'error',
        UserAction.created_at.between(start_date, end_date)
    ).group_by(UserAction.content).all()

    return {str(error[0]): error[1] for error in error_types if error[0]}


def _get_users_with_errors(session: Session, start_date: datetime, end_date: datetime):
    """Получение списка пользователей с ошибками"""
    users = session.query(distinct(UserAction.user_id)) \
        .filter(
        UserAction.action_type == 'error',
        UserAction.created_at.between(start_date, end_date)
    ).all()
    return [user[0] for user in users]
