# services/user_history_service.py
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from database.models import (
    UserAction,
    UserPseudonym,
    DialogueMetadata,
    DialogueContent,
    DataRetentionLog
)
from config.settings import (
    ANONYMIZATION_SETTINGS,
    DIALOGUE_SETTINGS,
    DATA_RETENTION
)
from services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)


class UserHistoryService:
    """
    Сервис для работы с историей пользователей с учетом конфиденциальности
    """

    def __init__(self, session: Session, encryption_service: Optional[EncryptionService] = None):
        """
        Инициализация сервиса истории пользователей

        Args:
            session: Сессия SQLAlchemy
            encryption_service: Сервис шифрования (создается при необходимости)
        """
        self.session = session
        self.encryption_service = encryption_service or EncryptionService(session)

        # Настройки конфиденциальности
        self.pseudonymize = ANONYMIZATION_SETTINGS.get('enable_pseudonymization', True)
        self.max_context_messages = DIALOGUE_SETTINGS.get('max_context_messages', 30)
        self.message_retention_days = DATA_RETENTION.get('message_retention_days', 90)

    async def get_user_interaction_history(
            self,
            user_identifier: int,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Получение обезличенной истории взаимодействий пользователя

        Args:
            user_identifier: ID пользователя или pseudonym_id
            start_date: Начало периода (опционально)
            end_date: Конец периода (опционально)

        Returns:
            Словарь с историей взаимодействий
        """
        try:
            # Получаем pseudonym_id
            pseudonym_id = await self._get_pseudonym_id(user_identifier)

            # Устанавливаем границы периода
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=self.message_retention_days)
            if not end_date:
                end_date = datetime.utcnow()

            # Получаем действия пользователя
            user_actions = await self._get_anonymized_actions(pseudonym_id, start_date, end_date)

            # Получаем историю диалогов
            dialogue_history = await self._get_dialogue_history(pseudonym_id, start_date, end_date)

            # Получаем историю управления данными
            retention_logs = await self._get_retention_logs(pseudonym_id)

            return {
                'pseudonym_id': pseudonym_id,
                'actions': user_actions,
                'dialogues': dialogue_history,
                'retention_logs': retention_logs
            }

        except Exception as e:
            logger.error(f"Error getting user interaction history: {e}")
            return {
                'pseudonym_id': None,
                'actions': [],
                'dialogues': [],
                'retention_logs': []
            }

    async def _get_pseudonym_id(self, user_identifier: int) -> Optional[str]:
        """
        Получение pseudonym_id для пользователя

        Args:
            user_identifier: ID пользователя

        Returns:
            Pseudonym ID или None
        """
        try:
            # Проверяем, является ли идентификатор уже pseudonym_id
            if isinstance(user_identifier, str) and len(user_identifier) == 36:
                return user_identifier

            # Ищем связь с pseudonym
            pseudonym = self.session.query(UserPseudonym) \
                .filter(UserPseudonym.user_id == user_identifier) \
                .first()

            return pseudonym.pseudonym_id if pseudonym else None

        except Exception as e:
            logger.error(f"Error getting pseudonym ID: {e}")
            return None

    async def _get_anonymized_actions(
            self,
            pseudonym_id: str,
            start_date: datetime,
            end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Получение обезличенных действий пользователя

        Args:
            pseudonym_id: Идентификатор псевдонима
            start_date: Начало периода
            end_date: Конец периода

        Returns:
            Список обезличенных действий
        """
        try:
            # Получаем действия пользователя
            actions = self.session.query(
                UserAction.action_type,
                UserAction.created_at,
                func.length(UserAction.content).label('content_length')
            ).join(
                UserPseudonym,
                UserPseudonym.user_id == UserAction.user_id
            ).filter(
                UserPseudonym.pseudonym_id == pseudonym_id,
                UserAction.created_at.between(start_date, end_date)
            ).order_by(
                UserAction.created_at
            ).all()

            # Преобразуем в список словарей
            return [
                {
                    'action_type': action.action_type,
                    'timestamp': action.created_at.isoformat(),
                    'content_length': action.content_length
                }
                for action in actions
            ]

        except Exception as e:
            logger.error(f"Error getting anonymized actions: {e}")
            return []

    async def _get_dialogue_history(
            self,
            pseudonym_id: str,
            start_date: datetime,
            end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Получение обезличенной истории диалогов

        Args:
            pseudonym_id: Идентификатор псевдонима
            start_date: Начало периода
            end_date: Конец периода

        Returns:
            Список обезличенных диалогов
        """
        try:
            # Получаем метаданные диалогов
            dialogues = self.session.query(
                DialogueMetadata.message_hash,
                DialogueMetadata.role,
                DialogueMetadata.timestamp,
                func.length(DialogueContent.encrypted_content).label('content_length')
            ).join(
                DialogueContent,
                DialogueMetadata.content_id == DialogueContent.id
            ).filter(
                DialogueMetadata.pseudonym_id == pseudonym_id,
                DialogueMetadata.timestamp.between(start_date, end_date)
            ).order_by(
                DialogueMetadata.timestamp
            ).limit(
                self.max_context_messages
            ).all()

            # Преобразуем в список словарей
            return [
                {
                    'message_hash': dialogue.message_hash,
                    'role': dialogue.role,
                    'timestamp': dialogue.timestamp.isoformat(),
                    'content_length': dialogue.content_length
                }
                for dialogue in dialogues
            ]

        except Exception as e:
            logger.error(f"Error getting dialogue history: {e}")
            return []

    async def _get_retention_logs(self, pseudonym_id: str) -> List[Dict[str, Any]]:
        """
        Получение логов управления данными

        Args:
            pseudonym_id: Идентификатор псевдонима

        Returns:
            Список логов управления данными
        """
        try:
            # Получаем логи управления данными
            logs = self.session.query(
                DataRetentionLog.operation_type,
                DataRetentionLog.records_affected,
                DataRetentionLog.date_range_start,
                DataRetentionLog.date_range_end,
                DataRetentionLog.operation_date,
                DataRetentionLog.reason
            ).filter(
                DataRetentionLog.pseudonym_id == pseudonym_id
            ).order_by(
                DataRetentionLog.operation_date.desc()
            ).limit(10).all()

            # Преобразуем в список словарей
            return [
                {
                    'operation_type': log.operation_type,
                    'records_affected': log.records_affected,
                    'date_range_start': log.date_range_start.isoformat() if log.date_range_start else None,
                    'date_range_end': log.date_range_end.isoformat() if log.date_range_end else None,
                    'operation_date': log.operation_date.isoformat(),
                    'reason': log.reason
                }
                for log in logs
            ]

        except Exception as e:
            logger.error(f"Error getting retention logs: {e}")
            return []

    async def get_data_retention_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики по управлению данными

        Returns:
            Dict со статистикой
        """
        try:
            # Общая статистика операций
            total_stats = self.session.query(
                func.count(DataRetentionLog.id).label('total_operations'),
                func.sum(DataRetentionLog.records_affected).label('total_records'),
                func.max(DataRetentionLog.operation_date).label('last_operation')
            ).first()

            # Статистика по типам операций
            operations_by_type = self.session.query(
                DataRetentionLog.operation_type,
                func.count(DataRetentionLog.id).label('operation_count'),
                func.sum(DataRetentionLog.records_affected).label('records_affected')
            ).group_by(DataRetentionLog.operation_type).all()

            # Статистика за последний месяц
            month_ago = datetime.utcnow() - timedelta(days=30)
            recent_stats = self.session.query(
                func.count(DataRetentionLog.id).label('recent_operations'),
                func.sum(DataRetentionLog.records_affected).label('recent_records')
            ).filter(
                DataRetentionLog.operation_date >= month_ago
            ).first()

            return {
                'total_operations': total_stats[0] or 0,
                'total_records_affected': total_stats[1] or 0,
                'last_operation_date': total_stats[2].isoformat() if total_stats[2] else None,
                'operations_by_type': {
                    op_type: {
                        'count': count,
                        'records_affected': records
                    }
                    for op_type, count, records in operations_by_type
                },
                'last_30_days': {
                    'operations': recent_stats[0] or 0,
                    'records_affected': recent_stats[1] or 0
                }
            }

        except Exception as e:
            logger.error(f"Error getting data retention statistics: {e}")
            return {
                'total_operations': 0,
                'total_records_affected': 0,
                'last_operation_date': None,
                'operations_by_type': {},
                'last_30_days': {
                    'operations': 0,
                    'records_affected': 0
                }
            }
