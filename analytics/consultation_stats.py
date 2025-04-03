import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, and_, or_
from sqlalchemy.sql import label

from database.models import (
    UserAction,
    UserPseudonym,
    DialogueMetadata,
    DialogueContent
)
from config.settings import (
    ANALYTICS_SETTINGS,
    ANONYMIZATION_SETTINGS,
    DIALOGUE_SETTINGS
)

logger = logging.getLogger(__name__)


def get_consultation_analytics(session: Session, start_date: datetime, end_date: datetime):
    """
    Комплексная аналитика консультаций с учетом конфиденциальности

    Args:
        session: SQLAlchemy сессия
        start_date: Начало периода
        end_date: Конец периода

    Returns:
        Dict с аналитикой консультаций
    """
    try:
        # Настройки конфиденциальности
        pseudonymize = ANONYMIZATION_SETTINGS.get('enable_pseudonymization', True)
        max_context_messages = DIALOGUE_SETTINGS.get('max_context_messages', 30)

        # Базовая статистика консультаций
        total_consultations = _count_total_consultations(session, start_date, end_date, pseudonymize)

        # Распределение длительности консультаций
        consultation_length_stats = _analyze_consultation_length(session, start_date, end_date, pseudonymize)

        # Тематический анализ (на основе метаданных)
        topic_distribution = _get_topic_distribution(session, start_date, end_date, pseudonymize)

        # Анализ контекста консультаций
        context_analysis = _analyze_consultation_context(
            session,
            start_date,
            end_date,
            pseudonymize,
            max_context_messages
        )

        # Временные паттерны консультаций
        temporal_patterns = _get_temporal_consultation_patterns(session, start_date, end_date, pseudonymize)

        # Статистика повторных консультаций
        repeat_consultation_stats = _analyze_repeat_consultations(session, start_date, end_date, pseudonymize)

        return {
            'total_consultations': total_consultations,
            'consultation_length': consultation_length_stats,
            'topic_distribution': topic_distribution,
            'context_analysis': context_analysis,
            'temporal_patterns': temporal_patterns,
            'repeat_consultations': repeat_consultation_stats
        }

    except Exception as e:
        logger.error(f"Error getting consultation analytics: {e}")
        return {
            'total_consultations': 0,
            'consultation_length': {},
            'topic_distribution': {},
            'context_analysis': {},
            'temporal_patterns': {},
            'repeat_consultations': {}
        }


def _count_total_consultations(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        pseudonymize: bool
) -> int:
    """
    Подсчет общего количества консультаций с учетом конфиденциальности
    """
    try:
        # Идентификатор для группировки
        identifier = (
            UserPseudonym.pseudonym_id if pseudonymize
            else UserAction.user_id
        )

        total_consultations = session.query(func.count(distinct(UserAction.id))) \
                                 .join(
            UserPseudonym,
            UserPseudonym.user_id == UserAction.user_id if pseudonymize else True
        ) \
                                 .filter(
            UserAction.action_type.like('%consultation%'),
            UserAction.created_at.between(start_date, end_date)
        ) \
                                 .scalar() or 0

        return total_consultations
    except Exception as e:
        logger.error(f"Error counting total consultations: {e}")
        return 0


def _analyze_consultation_length(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        pseudonymize: bool
):
    """
    Анализ длительности консультаций с учетом конфиденциальности
    """
    # Идентификатор для группировки
    identifier = (
        UserPseudonym.pseudonym_id if pseudonymize
        else UserAction.user_id
    )

    # Анализ длины сообщений в консультациях
    length_stats = session.query(
        label('min_length', func.min(func.length(UserAction.content))),
        label('max_length', func.max(func.length(UserAction.content))),
        label('avg_length', func.avg(func.length(UserAction.content))),
        label('total_consultations', func.count(distinct(UserAction.id)))
    ).join(
        UserPseudonym,
        UserPseudonym.user_id == UserAction.user_id if pseudonymize else True
    ).filter(
        UserAction.action_type.like('%consultation%'),
        UserAction.created_at.between(start_date, end_date),
        UserAction.content.isnot(None)
    ).first()

    return {
        'min_length': length_stats[0] or 0,
        'max_length': length_stats[1] or 0,
        'avg_length': round(length_stats[2] or 0, 2),
        'total_consultations': length_stats[3] or 0
    }


def _get_topic_distribution(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        pseudonymize: bool
):
    """
    Распределение тем консультаций с учетом конфиденциальности

    Примечание: Важно не раскрывать содержание, а только общие характеристики
    """
    # Идентификатор для группировки
    identifier = (
        UserPseudonym.pseudonym_id if pseudonymize
        else UserAction.user_id
    )

    # Группировка по первым словам или ключевым тегам
    topic_stats = session.query(
        func.substring(UserAction.content, 1, 20),  # Первые 20 символов как приближенная тема
        func.count(distinct(UserAction.id)).label('consultation_count'),
        func.count(distinct(identifier)).label('unique_users')
    ).join(
        UserPseudonym,
        UserPseudonym.user_id == UserAction.user_id if pseudonymize else True
    ).filter(
        UserAction.action_type.like('%consultation%'),
        UserAction.created_at.between(start_date, end_date),
        UserAction.content.isnot(None)
    ).group_by(
        func.substring(UserAction.content, 1, 20)
    ).order_by(
        func.count(distinct(UserAction.id)).desc()
    ).limit(10).all()

    return {
        topic[:20]: {
            'consultation_count': count,
            'unique_users': unique_users
        }
        for topic, count, unique_users in topic_stats
    }


def _analyze_consultation_context(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        pseudonymize: bool,
        max_context_messages: int
):
    """
    Анализ контекста консультаций с учетом конфиденциальности
    """
    try:
        # Сначала подсчитаем общее количество диалогов
        total_dialogues_query = session.query(
            func.count(distinct(DialogueMetadata.pseudonym_id))
        ).filter(
            DialogueMetadata.timestamp.between(start_date, end_date)
        )

        total_dialogues = total_dialogues_query.scalar() or 0

        # Затем подсчитаем среднее количество сообщений на диалог
        # Для этого сначала получим количество сообщений для каждого псевдонима
        messages_per_dialogue = session.query(
            DialogueMetadata.pseudonym_id,
            func.count(DialogueMetadata.id).label('message_count')
        ).filter(
            DialogueMetadata.timestamp.between(start_date, end_date)
        ).group_by(
            DialogueMetadata.pseudonym_id
        ).all()

        # Вычисляем среднее значение
        if messages_per_dialogue:
            total_messages = sum(count for _, count in messages_per_dialogue)
            avg_messages = total_messages / len(messages_per_dialogue)
        else:
            avg_messages = 0

        return {
            'total_dialogues': total_dialogues,
            'avg_messages_per_dialogue': round(avg_messages, 2),
            'max_context_messages': max_context_messages
        }

    except Exception as e:
        logger.error(f"Error analyzing consultation context: {e}")
        return {
            'total_dialogues': 0,
            'avg_messages_per_dialogue': 0,
            'max_context_messages': max_context_messages
        }


def _get_temporal_consultation_patterns(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        pseudonymize: bool
):
    """
    Временные паттерны консультаций с учетом конфиденциальности
    """
    # Идентификатор для группировки
    identifier = (
        UserPseudonym.pseudonym_id if pseudonymize
        else UserAction.user_id
    )

    # Анализ распределения консультаций по дням недели и часам
    day_hour_stats = session.query(
        func.extract('dow', UserAction.created_at).label('day_of_week'),
        func.extract('hour', UserAction.created_at).label('hour'),
        func.count(distinct(UserAction.id)).label('consultation_count'),
        func.count(distinct(identifier)).label('unique_users')
    ).join(
        UserPseudonym,
        UserPseudonym.user_id == UserAction.user_id if pseudonymize else True
    ).filter(
        UserAction.action_type.like('%consultation%'),
        UserAction.created_at.between(start_date, end_date)
    ).group_by('day_of_week', 'hour').all()

    # Дни недели для более читаемого вывода
    days_map = {
        0: 'Sunday', 1: 'Monday', 2: 'Tuesday',
        3: 'Wednesday', 4: 'Thursday',
        5: 'Friday', 6: 'Saturday'
    }

    # Преобразование в структурированный словарь
    temporal_patterns = {}
    for row in day_hour_stats:
        day = days_map[int(row[0])]
        hour = int(row[1])

        if day not in temporal_patterns:
            temporal_patterns[day] = {}

        temporal_patterns[day][hour] = {
            'consultation_count': row[2],
            'unique_users': row[3]
        }

    return temporal_patterns


def _analyze_repeat_consultations(
        session: Session,
        start_date: datetime,
        end_date: datetime,
        pseudonymize: bool
):
    """
    Анализ повторных консультаций с учетом конфиденциальности
    """
    try:
        # Сначала создаем подзапрос для подсчета количества консультаций на пользователя
        if pseudonymize:
            # Запрос с псевдонимизацией
            subquery = session.query(
                UserPseudonym.pseudonym_id.label('user_identifier'),
                func.count(distinct(UserAction.id)).label('consultation_count')
            ).join(
                UserAction,
                UserPseudonym.user_id == UserAction.user_id
            ).filter(
                UserAction.action_type.like('%consultation%'),
                UserAction.created_at.between(start_date, end_date)
            ).group_by(
                UserPseudonym.pseudonym_id
            ).subquery()
        else:
            # Запрос без псевдонимизации
            subquery = session.query(
                UserAction.user_id.label('user_identifier'),
                func.count(distinct(UserAction.id)).label('consultation_count')
            ).filter(
                UserAction.action_type.like('%consultation%'),
                UserAction.created_at.between(start_date, end_date)
            ).group_by(
                UserAction.user_id
            ).subquery()

        # Теперь анализируем полученные данные
        total_users = session.query(func.count()).select_from(subquery).scalar() or 0
        repeat_users = session.query(func.count()).select_from(subquery).filter(
            subquery.c.consultation_count > 1
        ).scalar() or 0

        # Вычисляем коэффициент повторения
        repeat_rate = (repeat_users / total_users * 100) if total_users > 0 else 0

        return {
            'total_users': total_users,
            'repeat_users': repeat_users,
            'repeat_rate': round(repeat_rate, 2)
        }

    except Exception as e:
        logger.error(f"Error analyzing repeat consultations: {e}")
        return {
            'total_users': 0,
            'repeat_users': 0,
            'repeat_rate': 0.0
        }
