import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from database.models import (
    UserAction,
    UserPseudonym,
    DialogueMetadata,
    DialogueContent,
    DataRetentionLog,
    Feedback,
    UserCredits,
    UserSubscription
)
from config.settings import (
    DATA_RETENTION,
    ANONYMIZATION_SETTINGS
)
from services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)


class DataRetentionService:
    """
    Сервис для управления жизненным циклом данных
    """

    def __init__(
            self,
            session: Session,
            encryption_service: Optional[EncryptionService] = None
    ):
        """
        Инициализация сервиса управления данными

        Args:
            session: Сессия SQLAlchemy
            encryption_service: Сервис шифрования (создается при необходимости)
        """
        self.session = session
        self.encryption_service = encryption_service or EncryptionService(session)

        # Параметры хранения данных из настроек
        self.message_retention_days = DATA_RETENTION.get(
            'message_retention_days',
            90
        )
        self.inactive_user_anonymization_days = DATA_RETENTION.get(
            'inactive_user_anonymization_days',
            365
        )
        self.log_retention_days = DATA_RETENTION.get(
            'log_retention_days',
            365
        )

    async def execute_retention_policy(self) -> Dict[str, int]:
        """
        Выполнение политики хранения данных

        Returns:
            Статистика выполненных операций
        """
        retention_stats = {
            'anonymized_users': 0,
            'deleted_messages': 0,
            'deleted_actions': 0,
            'deleted_logs': 0
        }

        try:
            # Текущая дата
            now = datetime.utcnow()

            # 1. Анонимизация неактивных пользователей
            retention_stats['anonymized_users'] = await self._anonymize_inactive_users(now)

            # 2. Удаление старых сообщений
            retention_stats['deleted_messages'] = await self._delete_old_messages(now)

            # 3. Удаление старых действий пользователей
            retention_stats['deleted_actions'] = await self._delete_old_actions(now)

            # 4. Очистка логов
            retention_stats['deleted_logs'] = await self._delete_old_logs(now)

            # Логирование операции
            log_entry = DataRetentionLog(
                operation_type='full_retention_policy',
                records_affected=sum(retention_stats.values()),
                operation_date=now,
                reason='Automated data retention policy execution'
            )
            self.session.add(log_entry)
            self.session.commit()

            logger.info(f"Data retention policy executed: {retention_stats}")
            return retention_stats

        except Exception as e:
            logger.error(f"Error executing retention policy: {e}")
            self.session.rollback()
            return retention_stats

    async def _anonymize_inactive_users(self, current_time: datetime) -> int:
        """
        Анонимизация неактивных пользователей

        Args:
            current_time: Текущее время

        Returns:
            Количество анонимизированных пользователей
        """
        try:
            # Граница неактивности
            inactivity_threshold = current_time - timedelta(
                days=self.inactive_user_anonymization_days
            )

            # Находим неактивных пользователей
            inactive_users = self.session.query(UserPseudonym) \
                .join(UserAction, UserPseudonym.user_id == UserAction.user_id) \
                .group_by(UserPseudonym) \
                .having(
                func.max(UserAction.created_at) < inactivity_threshold
            ).all()

            anonymized_count = 0
            for user in inactive_users:
                # Очищаем связь с реальным ID
                user.user_id = None
                anonymized_count += 1

            if anonymized_count > 0:
                self.session.commit()
                logger.info(f"Anonymized {anonymized_count} inactive users")

            return anonymized_count

        except Exception as e:
            logger.error(f"Error anonymizing inactive users: {e}")
            return 0

    async def _delete_old_messages(self, current_time: datetime) -> int:
        """
        Удаление старых сообщений

        Args:
            current_time: Текущее время

        Returns:
            Количество удаленных сообщений
        """
        try:
            # Граница давности сообщений
            message_threshold = current_time - timedelta(
                days=self.message_retention_days
            )

            # Находим и удаляем старые сообщения
            old_messages = self.session.query(DialogueMetadata) \
                .filter(DialogueMetadata.timestamp < message_threshold) \
                .all()

            deleted_count = 0
            for message in old_messages:
                # Удаляем связанный контент
                if message.content:
                    self.session.delete(message.content)

                # Удаляем метаданные
                self.session.delete(message)
                deleted_count += 1

            if deleted_count > 0:
                self.session.commit()
                logger.info(f"Deleted {deleted_count} old messages")

            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting old messages: {e}")
            return 0

    async def _delete_old_actions(self, current_time: datetime) -> int:
        """
        Удаление старых действий пользователей

        Args:
            current_time: Текущее время

        Returns:
            Количество удаленных действий
        """
        try:
            # Граница давности действий
            action_threshold = current_time - timedelta(
                days=self.message_retention_days
            )

            # Удаляем старые действия
            deleted_count = self.session.query(UserAction) \
                .filter(UserAction.created_at < action_threshold) \
                .delete(synchronize_session=False)

            if deleted_count > 0:
                self.session.commit()
                logger.info(f"Deleted {deleted_count} old user actions")

            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting old actions: {e}")
            return 0

    async def _delete_old_logs(self, current_time: datetime) -> int:
        """
        Удаление старых логов

        Args:
            current_time: Текущее время

        Returns:
            Количество удаленных логов
        """
        try:
            # Граница давности логов
            log_threshold = current_time - timedelta(
                days=self.log_retention_days
            )

            # Удаляем старые логи
            deleted_count = self.session.query(DataRetentionLog) \
                .filter(DataRetentionLog.operation_date < log_threshold) \
                .delete(synchronize_session=False)

            if deleted_count > 0:
                self.session.commit()
                logger.info(f"Deleted {deleted_count} old retention logs")

            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting old logs: {e}")
            return 0

    async def get_data_retention_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики по управлению данными

        Returns:
            Словарь со статистикой операций
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

    def manual_user_data_cleanup(
            self,
            user_id: int,
            reason: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Ручная очистка данных пользователя (кроме подписок и транзакций)

        Args:
            user_id: ID пользователя
            reason: Причина удаления

        Returns:
            Статистика удаленных записей
        """
        try:
            cleanup_stats = {
                'deleted_messages': 0,
                'deleted_actions': 0,
                'deleted_feedbacks': 0
            }

            # Сначала проверяем и создаем pseudonym, если его нет
            pseudonym = self.session.query(UserPseudonym).filter_by(user_id=user_id).first()
            if not pseudonym:
                # Создаем новый pseudonym, если его нет
                pseudonym = UserPseudonym(user_id=user_id, pseudonym_id=str(uuid.uuid4()))
                self.session.add(pseudonym)

            pseudonym_id = pseudonym.pseudonym_id

            # Удаление сообщений через DialogueMetadata
            deleted_messages = self.session.query(DialogueMetadata) \
                .filter(DialogueMetadata.pseudonym_id == pseudonym_id) \
                .delete(synchronize_session=False)
            cleanup_stats['deleted_messages'] = deleted_messages

            # Удаление действий пользователя
            deleted_actions = self.session.query(UserAction) \
                .filter(UserAction.user_id == user_id) \
                .delete(synchronize_session=False)
            cleanup_stats['deleted_actions'] = deleted_actions

            # Удаление обратной связи
            deleted_feedbacks = self.session.query(Feedback) \
                .filter(Feedback.user_id == user_id) \
                .delete(synchronize_session=False)
            cleanup_stats['deleted_feedbacks'] = deleted_feedbacks

            # Создаем запись в логе управления данными
            log_entry = DataRetentionLog(
                pseudonym_id=pseudonym_id,
                operation_type='manual_user_cleanup',
                records_affected=sum(cleanup_stats.values()),
                reason=reason or 'Manual user data cleanup',
                operation_date=datetime.utcnow()
            )
            self.session.add(log_entry)

            # Фиксируем изменения
            self.session.commit()

            logger.info(f"Manual cleanup for user {user_id}: {cleanup_stats}")
            return cleanup_stats

        except Exception as e:
            logger.error(f"Error in manual user data cleanup: {e}", exc_info=True)
            self.session.rollback()
            return {
                'deleted_messages': 0,
                'deleted_actions': 0,
                'deleted_feedbacks': 0
            }
