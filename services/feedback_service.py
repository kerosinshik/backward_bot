import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from database.models import (
    Feedback,
    UserPseudonym
)
from config.settings import (
    ANONYMIZATION_SETTINGS,
    DATA_RETENTION
)
from services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)


class FeedbackService:
    """
    Сервис для работы с обратной связью с учетом конфиденциальности
    """

    def __init__(
            self,
            session: Session,
            encryption_service: Optional[EncryptionService] = None
    ):
        """
        Инициализация сервиса обратной связи

        Args:
            session: Сессия SQLAlchemy
            encryption_service: Сервис шифрования (создается при необходимости)
        """
        self.session = session
        self.encryption_service = encryption_service or EncryptionService(session)

        # Настройки конфиденциальности
        self.pseudonymize = ANONYMIZATION_SETTINGS.get(
            'enable_pseudonymization',
            True
        )
        self.retention_days = DATA_RETENTION.get(
            'message_retention_days',
            90
        )

    async def create_feedback(
            self,
            user_id: int,
            feedback_text: str,
            feedback_type: str = 'general',
            context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создание обратной связи с учетом конфиденциальности

        Args:
            user_id: ID пользователя
            feedback_text: Текст обратной связи
            feedback_type: Тип обратной связи
            context: Дополнительный контекст (опционально)

        Returns:
            Словарь с информацией о созданном отзыве
        """
        try:
            # Получаем или создаем pseudonym_id
            pseudonym_id = await self.encryption_service.ensure_pseudonym(user_id)

            # Шифруем содержимое обратной связи
            encrypted_text = await self.encryption_service.encrypt_message(
                feedback_text,
                pseudonym_id
            )

            # Шифруем дополнительный контекст (если есть)
            encrypted_context = None
            if context:
                encrypted_context = await self.encryption_service.encrypt_message(
                    context,
                    pseudonym_id
                )

            # Создаем запись обратной связи
            feedback = Feedback(
                user_id=user_id if not self.pseudonymize else None,
                feedback_type=feedback_type,
                feedback_text=encrypted_text,
                context=encrypted_context,
                feedback_date=datetime.utcnow()
            )

            # Сохраняем в базе данных
            self.session.add(feedback)
            self.session.commit()

            return {
                'id': feedback.id,
                'pseudonym_id': pseudonym_id,
                'feedback_type': feedback_type,
                'created_at': feedback.feedback_date.isoformat()
            }

        except Exception as e:
            logger.error(f"Error creating feedback: {e}")
            self.session.rollback()
            return {}

    async def get_feedback(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            feedback_type: Optional[str] = None,
            limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Получение обезличенной обратной связи

        Args:
            start_date: Начало периода (опционально)
            end_date: Конец периода (опционально)
            feedback_type: Тип обратной связи (опционально)
            limit: Максимальное количество записей

        Returns:
            Список обезличенных отзывов
        """
        try:
            # Устанавливаем границы периода, если не указаны
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=self.retention_days)
            if not end_date:
                end_date = datetime.utcnow()

            # Базовый запрос с фильтрацией
            query = self.session.query(
                Feedback.id,
                Feedback.feedback_type,
                func.length(Feedback.feedback_text).label('feedback_length'),
                Feedback.feedback_date
            )

            # Добавляем фильтры
            filters = []
            filters.append(Feedback.feedback_date.between(start_date, end_date))

            if feedback_type:
                filters.append(Feedback.feedback_type == feedback_type)

            # Применяем фильтры
            query = query.filter(and_(*filters))

            # Лимитируем и сортируем
            query = query.order_by(Feedback.feedback_date.desc()).limit(limit)

            # Выполняем запрос
            feedbacks = query.all()

            # Преобразуем в список словарей
            return [
                {
                    'id': f.id,
                    'type': f.feedback_type,
                    'length': f.feedback_length,
                    'date': f.feedback_date.isoformat()
                }
                for f in feedbacks
            ]

        except Exception as e:
            logger.error(f"Error getting feedback: {e}")
            return []

    async def analyze_feedback(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Анализ обратной связи с учетом конфиденциальности

        Args:
            start_date: Начало периода (опционально)
            end_date: Конец периода (опционально)

        Returns:
            Словарь с агрегированной статистикой обратной связи
        """
        try:
            # Устанавливаем границы периода, если не указаны
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=self.retention_days)
            if not end_date:
                end_date = datetime.utcnow()

            # Анализ типов обратной связи
            type_stats = self.session.query(
                Feedback.feedback_type,
                func.count(Feedback.id).label('total_count'),
                func.avg(func.length(Feedback.feedback_text)).label('avg_length')
            ).filter(
                Feedback.feedback_date.between(start_date, end_date)
            ).group_by(
                Feedback.feedback_type
            ).all()

            # Анализ распределения по времени
            time_distribution = self.session.query(
                func.date_trunc('day', Feedback.feedback_date).label('day'),
                func.count(Feedback.id).label('count')
            ).filter(
                Feedback.feedback_date.between(start_date, end_date)
            ).group_by('day').all()

            # Преобразование результатов
            return {
                'types': {
                    type_name: {
                        'total_count': count,
                        'avg_length': round(avg_length, 2)
                    }
                    for type_name, count, avg_length in type_stats
                },
                'time_distribution': {
                    day.date().isoformat(): count
                    for day, count in time_distribution
                }
            }

        except Exception as e:
            logger.error(f"Error analyzing feedback: {e}")
            return {
                'types': {},
                'time_distribution': {}
            }

    async def export_feedback(
            self,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            feedback_type: Optional[str] = None
    ) -> bytes:
        """
        Экспорт обезличенной обратной связи

        Args:
            start_date: Начало периода (опционально)
            end_date: Конец периода (опционально)
            feedback_type: Тип обратной связи (опционально)

        Returns:
            Байты CSV-файла
        """
        try:
            import csv
            import io

            # Получаем обезличенную обратную связь
            feedbacks = await self.get_feedback(
                start_date,
                end_date,
                feedback_type
            )

            # Создаем буфер в памяти
            output = io.StringIO()
            writer = csv.writer(output)

            # Заголовки
            writer.writerow([
                'ID',
                'Тип',
                'Длина',
                'Дата'
            ])

            # Записываем данные
            for feedback in feedbacks:
                writer.writerow([
                    feedback['id'],
                    feedback['type'],
                    feedback['length'],
                    feedback['date']
                ])

            # Возвращаем байты CSV
            return output.getvalue().encode('utf-8')

        except Exception as e:
            logger.error(f"Error exporting feedback: {e}")
            return b''

    async def delete_user_feedback(self, user_id: int) -> int:
        """
        Удаление всей обратной связи пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Количество удаленных записей
        """
        try:
            # Находим pseudonym_id
            pseudonym_id = await self.encryption_service.ensure_pseudonym(user_id)

            # Удаляем связанную обратную связь
            deleted_count = self.session.query(Feedback) \
                .filter(Feedback.user_id == user_id) \
                .delete(synchronize_session=False)

            self.session.commit()

            logger.info(f"Deleted {deleted_count} feedback entries for user {user_id}")

            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting user feedback: {e}")
            self.session.rollback()
            return 0
