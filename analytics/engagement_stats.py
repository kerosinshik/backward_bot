import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from database.models import UserAction

logger = logging.getLogger(__name__)

def get_engagement_stats(session: Session, start_date: datetime, end_date: datetime):
    """Получение статистики вовлеченности"""
    try:
        return {
            'total_actions': _count_total_actions(session, start_date, end_date),
            'command_usage': _get_command_usage(session, start_date, end_date),
            'peak_hours': _get_peak_hours(session, start_date, end_date),
            'consultation_stats': _get_consultation_stats(session, start_date, end_date)
        }
    except Exception as e:
        logger.error(f"Error getting engagement stats: {e}")
        return {
            'total_actions': 0,
            'command_usage': {},
            'peak_hours': {},
            'consultation_stats': {}
        }

def _count_total_actions(session: Session, start_date: datetime, end_date: datetime) -> int:
    """Подсчет общего количества действий"""
    return session.query(UserAction) \
        .filter(UserAction.created_at.between(start_date, end_date)) \
        .count()

def _get_command_usage(session: Session, start_date: datetime, end_date: datetime):
    """Статистика использования команд"""
    commands = session.query(
        UserAction.content,
        func.count(UserAction.id)
    ).filter(
        UserAction.action_type == 'command',
        UserAction.created_at.between(start_date, end_date)
    ).group_by(UserAction.content).all()

    return {str(cmd[0]): cmd[1] for cmd in commands if cmd[0]}

def _get_peak_hours(session: Session, start_date: datetime, end_date: datetime):
    """Анализ пиковых часов активности"""
    peak_hours = session.query(
        func.extract('hour', func.timezone('Europe/Moscow', UserAction.created_at)).label('hour'),
        func.count(UserAction.id).label('count')
    ).filter(
        UserAction.created_at.between(start_date, end_date)
    ).group_by('hour').all()

    return {int(hour): count for hour, count in peak_hours}

def _get_consultation_stats(session: Session, start_date: datetime, end_date: datetime):
    """Статистика консультаций"""
    total = session.query(func.count(UserAction.id)) \
        .filter(
            UserAction.action_type == 'consultation_start',
            UserAction.created_at.between(start_date, end_date)
        ).scalar() or 0

    completed = session.query(func.count(UserAction.id)) \
        .filter(
            UserAction.action_type == 'consultation_complete',
            UserAction.created_at.between(start_date, end_date)
        ).scalar() or 0

    return {
        'total': total,
        'completed': completed,
        'completion_rate': (completed / total * 100) if total > 0 else 0,
        'avg_duration': _get_avg_consultation_length(session, start_date, end_date)
    }

def _get_avg_consultation_length(session: Session, start_date: datetime, end_date: datetime) -> float:
    """Расчет средней длительности консультации"""
    consultation_pairs = session.query(
        UserAction.user_id,
        func.min(UserAction.created_at).label('start_time'),
        func.max(UserAction.created_at).label('end_time')
    ).filter(
        UserAction.action_type.in_(['consultation_start', 'consultation_complete']),
        UserAction.created_at.between(start_date, end_date)
    ).group_by(UserAction.user_id).subquery()

    avg_duration = session.query(
        func.avg(
            func.extract(
                'epoch',
                consultation_pairs.c.end_time - consultation_pairs.c.start_time
            ) / 60
        )
    ).scalar() or 0.0

    return round(avg_duration, 2)
