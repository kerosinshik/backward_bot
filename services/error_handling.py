import logging
import traceback
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import (
    ErrorLog,
    UserPseudonym
)
from config.settings import (
    ANONYMIZATION_SETTINGS,
    DATA_RETENTION,
    ANALYTICS_SETTINGS
)

logger = logging.getLogger(__name__)

class ErrorHandlingService:
    """
    Сервис централизованной обработки и логирования ошибок
    """

    def __init__(self, session: Session):
        """
        Инициализация сервиса обработки ошибок

        Args:
            session: Сессия SQLAlchemy
        """
        self.session = session
        self.logger = logging.getLogger(__name__)

        # Настройки конфиденциальности
        self.pseudonymize = ANONYMIZATION_SETTINGS.get(
            'enable_pseudonymization',
            True
        )
        self.error_retention_days = DATA_RETENTION.get(
            'error_log_retention_days',
            90
        )

    def log_error(
            self,
            error: Exception,
            context: Optional[Dict[str, Any]] = None,
            user_id: Optional[int] = None,
            error_type: str = 'unhandled'
    ) -> str:
        """
        Логирование ошибки с сохранением в базу данных

        Args:
            error: Объект исключения
            context: Дополнительный контекст ошибки
            user_id: ID пользователя
            error_type: Тип ошибки

        Returns:
            Уникальный идентификатор ошибки
        """
        try:
            # Получаем pseudonym_id
            pseudonym_id = self._get_pseudonym_id(user_id) if user_id else None

            # Формируем подробную информацию об ошибке
            error_info = {
                'type': type(error).__name__,
                'message': str(error),
                'traceback': traceback.format_exc()
            }

            # Добавляем дополнительный контекст
            if context:
                error_info['context'] = self._sanitize_context(context)

            # Создаем запись об ошибке
            error_log = ErrorLog(
                user_id=user_id if not self.pseudonymize else None,
                pseudonym_id=pseudonym_id,
                error_type=error_type,
                error_details=str(error_info),
                created_at=datetime.utcnow()
            )

            # Сохраняем в базе данных
            self.session.add(error_log)
            self.session.commit()

            # Логируем в консоль
            self.logger.error(
                f"Error logged - Type: {error_type}, "
                f"Message: {error_info['message']}"
            )

            return str(error_log.id)

        except Exception as log_error:
            # Резервное логирование, если не удалось сохранить в БД
            self.logger.error(f"Failed to log error: {log_error}")
            self.logger.error(f"Original error: {error}")

            return str(hash(error))

    def _get_pseudonym_id(self, user_id: int) -> Optional[str]:
        """
        Получение pseudonym_id для пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Pseudonym ID или None
        """
        try:
            # Находим или создаем псевдоним
            pseudonym = self.session.query(UserPseudonym) \
                .filter_by(user_id=user_id) \
                .first()

            return pseudonym.pseudonym_id if pseudonym else None

        except Exception as e:
            self.logger.error(f"Error getting pseudonym: {e}")
            return None

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Санитарная обработка контекста для безопасного логирования

        Args:
            context: Исходный контекст

        Returns:
            Обработанный контекст
        """
        sanitized_context = {}

        # Список полей, которые никогда не логируются
        sensitive_keys = [
            'password', 'token', 'secret', 'api_key',
            'credit_card', 'personal_data'
        ]

        for key, value in context.items():
            # Пропускаем чувствительные поля
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                continue

            # Усекаем длинные значения
            if isinstance(value, str) and len(value) > 500:
                value = value[:500] + '...'

            sanitized_context[key] = value

        return sanitized_context

    def cleanup_old_errors(self) -> int:
        """
        Очистка старых записей об ошибках

        Returns:
            Количество удаленных записей
        """
        try:
            # Определяем период хранения
            cutoff_date = datetime.utcnow() - timedelta(days=self.error_retention_days)

            # Удаляем старые записи об ошибках
            deleted_count = self.session.query(ErrorLog) \
                .filter(ErrorLog.created_at < cutoff_date) \
                .delete(synchronize_session=False)

            self.session.commit()

            self.logger.info(f"Deleted {deleted_count} old error logs")
            return deleted_count

        except Exception as e:
            self.logger.error(f"Error cleaning up old errors: {e}")
            self.session.rollback()
            return 0

    def get_error_statistics(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Получение статистики по ошибкам

        Args:
            start_date: Начало периода
            end_date: Конец периода

        Returns:
            Словарь со статистикой ошибок
        """
        try:
            # Устанавливаем границы периода
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=30)
            if not end_date:
                end_date = datetime.utcnow()

            # Статистика по типам ошибок
            type_stats = self.session.query(
                ErrorLog.error_type,
                func.count(ErrorLog.id).label('total_count')
            ).filter(
                ErrorLog.created_at.between(start_date, end_date)
            ).group_by(
                ErrorLog.error_type
            ).all()

            # Распределение ошибок по времени
            time_distribution = self.session.query(
                func.date_trunc('day', ErrorLog.created_at).label('error_day'),
                func.count(ErrorLog.id).label('daily_count')
            ).filter(
                ErrorLog.created_at.between(start_date, end_date)
            ).group_by(
                'error_day'
            ).order_by(
                'error_day'
            ).all()

            return {
                'period': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'error_types': {
                    error_type: count
                    for error_type, count in type_stats
                },
                'time_distribution': {
                    day.date().isoformat(): count
                    for day, count in time_distribution
                },
                'total_errors': sum(count for _, count in type_stats)
            }

        except Exception as e:
            self.logger.error(f"Error getting error statistics: {e}")
            return {
                'period': {},
                'error_types': {},
                'time_distribution': {},
                'total_errors': 0
            }

    def handle_critical_error(
            self,
            error: Exception,
            context: Optional[Dict[str, Any]] = None
    ):
        """
        Обработка критических ошибок с дополнительными действиями

        Args:
            error: Объект исключения
            context: Дополнительный контекст
        """
        try:
            # Логируем критическую ошибку
            error_id = self.log_error(
                error,
                context,
                error_type='critical'
            )

            # Отправка уведомлений (можно расширить)
            self._send_critical_error_notification(error_id, error, context)

            # Возможные действия при критической ошибке
            # Например, перезапуск компонента, временная остановка сервиса и т.д.

        except Exception as handling_error:
            self.logger.critical(
                f"Failed to handle critical error: {handling_error}"
            )

    def _send_critical_error_notification(
            self,
            error_id: str,
            error: Exception,
            context: Optional[Dict[str, Any]] = None
    ):
        """
        Отправка уведомлений о критической ошибке
        (заглушка, может быть расширена для реальной отправки)

        Args:
            error_id: Уникальный идентификатор ошибки
            error: Объект исключения
            context: Дополнительный контекст
        """
        try:
            # В реальной реализации - отправка email, SMS, в Telegram и т.д.
            notification_message = (
                f"🚨 КРИТИЧЕСКАЯ ОШИБКА 🚨\n"
                f"ID: {error_id}\n"
                f"Тип: {type(error).__name__}\n"
                f"Сообщение: {str(error)}"
            )

            # Логирование как временная заглушка
            self.logger.critical(notification_message)

        except Exception as notify_error:
            self.logger.error(f"Failed to send error notification: {notify_error}")

    def log_api_error(
            self,
            service_name: str,
            error_details: str,
            user_id: Optional[int] = None,
            error_code: Optional[int] = None
    ):
        """
        Логирование критических ошибок API с дополнительной информацией

        Args:
            service_name: Название сервиса (например, 'Claude', 'Telegram')
            error_details: Подробности ошибки
            user_id: ID пользователя (опционально)
            error_code: Код ошибки (опционально)
        """
        try:
            error_log = {
                'service': service_name,
                'error_details': error_details,
                'user_id': user_id,
                'error_code': error_code
            }

            # Логируем как критическую ошибку
            logger.critical(f"API Error in {service_name}: {error_details}")

            # Если включена расширенная диагностика
            if ANALYTICS_SETTINGS.get('log_api_errors', True):
                # Можно добавить дополнительную логику логирования или отправки уведомлений
                pass

        except Exception as log_error:
            logger.error(f"Failed to log API error: {log_error}")
