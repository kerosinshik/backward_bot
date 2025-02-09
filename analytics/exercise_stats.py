import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import UserAction

logger = logging.getLogger(__name__)

def get_exercise_stats(session: Session, start_date: datetime, end_date: datetime):
    """Получение статистики по упражнениям"""
    try:
        started = _count_started_exercises(session, start_date, end_date)
        completed = _count_completed_exercises(session, start_date, end_date)

        return {
            'total_started': started,
            'total_completed': completed,
            'completion_rate': (completed / started * 100) if started > 0 else 0,
            'exercise_details': _get_exercise_details(session, start_date, end_date)
        }
    except Exception as e:
        logger.error(f"Error getting exercise stats: {e}")
        return {
            'total_started': 0,
            'total_completed': 0,
            'completion_rate': 0,
            'exercise_details': {}
        }

def _count_started_exercises(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет начатых упражнений"""
    return session.query(func.count(UserAction.id)) \
        .filter(
            UserAction.action_type == 'exercise_start',
            UserAction.created_at.between(start_date, end_date)
        ).scalar() or 0

def _count_completed_exercises(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет завершенных упражнений"""
    return session.query(func.count(UserAction.id)) \
        .filter(
            UserAction.action_type == 'exercise_complete',
            UserAction.created_at.between(start_date, end_date)
        ).scalar() or 0

def _get_exercise_details(session: Session, start_date: datetime, end_date: datetime):
    """Детальная статистика по упражнениям"""
    try:
        # Статистика по начатым упражнениям
        starts = session.query(
            UserAction.content,
            func.count(UserAction.id)
        ).filter(
            UserAction.action_type == 'exercise_start',
            UserAction.created_at.between(start_date, end_date)
        ).group_by(UserAction.content).all()

        # Статистика по завершенным упражнениям
        completes = session.query(
            UserAction.content,
            func.count(UserAction.id)
        ).filter(
            UserAction.action_type == 'exercise_complete',
            UserAction.created_at.between(start_date, end_date)
        ).group_by(UserAction.content).all()

        stats = {}
        for content, count in starts:
            if content:
                stats[content] = {'started': count, 'completed': 0}

        for content, count in completes:
            if content and content in stats:
                stats[content]['completed'] = count
                stats[content]['completion_rate'] = \
                    (count / stats[content]['started'] * 100) \
                    if stats[content]['started'] > 0 else 0

        return stats

    except Exception as e:
        logger.error(f"Error getting exercise details: {e}")
        return {}
