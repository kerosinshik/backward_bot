import logging
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session, sessionmaker
from contextlib import contextmanager
from analytics.user_stats import get_user_stats
from analytics.engagement_stats import get_engagement_stats
from analytics.exercise_stats import get_exercise_stats
from analytics.error_stats import get_error_stats
from database.models import UserAction

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, session: Session):
        """Инициализация сервиса аналитики"""
        self.Session = sessionmaker(bind=session.get_bind())
        self.timezone = pytz.timezone('Europe/Moscow')

    @contextmanager
    def session_scope(self):
        """Контекстный менеджер для сессий БД"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
            session.rollback()
            raise
        finally:
            session.close()

    def _get_empty_stats(self):
        """Возвращает пустую структуру статистики"""
        return {
            'date': datetime.now(self.timezone).strftime('%Y-%m-%d'),
            'users': {
                'total_unique': 0,
                'new_users': 0,
                'returning_users': 0,
                'active_users': 0
            },
            'engagement': {
                'total_actions': 0,
                'command_usage': {},
                'peak_hours': {}
            },
            'exercises': {
                'total_started': 0,
                'total_completed': 0,
                'completion_rate': 0
            },
            'errors': {
                'total_errors': 0,
                'error_types': {},
                'error_rate': 0
            }
        }

    async def log_action(self, user_id: int, action_type: str, content: str = None):
        """Логирование действия пользователя"""
        from database.models import UserAction

        with self.session_scope() as session:
            try:
                action = UserAction(
                    user_id=user_id,
                    action_type=action_type,
                    content=content,
                    created_at=datetime.now(pytz.UTC)
                )
                session.add(action)
                logger.debug(f"Logged action: {action_type} for user {user_id}")
            except Exception as e:
                logger.error(f"Error logging action: {e}")
                raise

    async def log_first_time_user(self, user_id: int):
        """Логирование первого использования"""
        from database.models import UserAction

        with self.session_scope() as session:
            try:
                # Проверяем, есть ли уже действия этого пользователя
                first_action = session.query(UserAction.id) \
                    .filter(UserAction.user_id == user_id) \
                    .first()

                if not first_action:
                    await self.log_action(user_id, 'first_time_user')
                    logger.info(f"Logged first time user: {user_id}")
            except Exception as e:
                logger.error(f"Error logging first time user: {e}")
                raise

    def get_daily_stats(self, date: datetime = None):
        """Получение ежедневной статистики"""
        try:
            if not date:
                date = datetime.now(self.timezone)
            elif date.tzinfo is None:
                date = self.timezone.localize(date)

            # Создаем начало и конец дня в локальной временной зоне
            start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1) - timedelta(microseconds=1)

            # Обязательно конвертируем в UTC для сравнения с БД
            start_date_utc = start_date.astimezone(pytz.UTC)
            end_date_utc = end_date.astimezone(pytz.UTC)

            logger.info(f"Getting stats from {start_date_utc} to {end_date_utc}")

            with self.session_scope() as session:
                # Для отладки
                test_query = session.query(UserAction).filter(
                    UserAction.created_at.between(start_date_utc, end_date_utc)
                ).all()
                logger.info(f"Found {len(test_query)} actions in time period")

                return {
                    'date': date.strftime('%Y-%m-%d'),
                    'users': get_user_stats(session, start_date_utc, end_date_utc),
                    'engagement': get_engagement_stats(session, start_date_utc, end_date_utc),
                    'exercises': get_exercise_stats(session, start_date_utc, end_date_utc),
                    'errors': get_error_stats(session, start_date_utc, end_date_utc)
                }

        except Exception as e:
            logger.error(f"Error getting daily stats: {e}")
            return self._get_empty_stats()
