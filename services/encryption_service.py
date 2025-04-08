# services/encryption_service.py
import logging
import os
import base64
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from database.models import (
    UserPseudonym,
    UserEncryptionKey,
    DialogueMetadata,
    DialogueContent
)
from config.settings import (
    ENCRYPTION_SETTINGS,
    ENCRYPTION_MASTER_KEY,
    ANONYMIZATION_SETTINGS,
    DIALOGUE_SETTINGS
)

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Сервис для обеспечения криптографической защиты данных
    """

    def __init__(self, session: Session):
        """
        Инициализация сервиса шифрования

        Args:
            session: Сессия SQLAlchemy
        """
        self.session = session

        # Настройки шифрования
        self.key_iterations = ENCRYPTION_SETTINGS.get(
            'key_derivation_iterations',
            100000
        )
        self.hash_algorithm = ENCRYPTION_SETTINGS.get(
            'pbkdf2_hash_algorithm',
            'SHA256'
        )
        self.encrypt_messages = DIALOGUE_SETTINGS.get(
            'encrypt_messages',
            True
        )

        # Проверка наличия мастер-ключа
        if not ENCRYPTION_MASTER_KEY:
            logger.warning("No master encryption key provided. Encryption will be disabled.")
            self.encrypt_messages = False

    def ensure_pseudonym(self, user_id: int) -> str:
        logging.info(f"ДИАГНОСТИКА: ensure_pseudonym для user_id={user_id}")
        try:
            # Проверяем, включена ли псевдонимизация
            is_pseudonymization_enabled = ANONYMIZATION_SETTINGS.get('enable_pseudonymization', True)
            logging.info(f"ДИАГНОСТИКА: псевдонимизация включена: {is_pseudonymization_enabled}")

            if not is_pseudonymization_enabled:
                logging.info(f"ДИАГНОСТИКА: псевдонимизация отключена, возвращаем user_id={user_id}")
                return str(user_id)

            # Ищем существующий псевдоним
            pseudonym = self.session.query(UserPseudonym) \
                .filter_by(user_id=user_id) \
                .first()

            # Создаем новый, если не существует
            if not pseudonym:
                logging.info(f"ДИАГНОСТИКА: псевдоним не найден для user_id={user_id}, создаем новый")
                new_pseudonym = UserPseudonym(
                    user_id=user_id,
                    pseudonym_id=str(uuid.uuid4())
                )
                self.session.add(new_pseudonym)
                self.session.commit()
                logging.info(f"ДИАГНОСТИКА: создан новый pseudonym_id={new_pseudonym.pseudonym_id}")
                return new_pseudonym.pseudonym_id

            logging.info(f"ДИАГНОСТИКА: найден существующий pseudonym_id={pseudonym.pseudonym_id}")
            return pseudonym.pseudonym_id

        except Exception as e:
            logger.error(f"Error ensuring pseudonym: {e}")
            logging.info(f"ДИАГНОСТИКА: ошибка в ensure_pseudonym, возвращаем str(user_id)={str(user_id)}")
            return str(user_id)

    def _derive_encryption_key(self, pseudonym_id: str) -> bytes:
        """
        Генерация криптографического ключа для псевдонима

        Args:
            pseudonym_id: Псевдоним пользователя

        Returns:
            Байты криптографического ключа
        """
        try:
            # Получаем user_id по pseudonym_id
            pseudonym = self.session.query(UserPseudonym) \
                .filter_by(pseudonym_id=pseudonym_id) \
                .first()

            if not pseudonym or not pseudonym.user_id:
                # Генерируем временный ключ, если не нашли пользователя
                logger.warning(f"Generating temporary key for pseudonym {pseudonym_id}")
                salt = os.urandom(16)
                hash_func = {
                    'SHA256': hashes.SHA256,
                    'SHA512': hashes.SHA512
                }.get(self.hash_algorithm, hashes.SHA256)

                kdf = PBKDF2HMAC(
                    algorithm=hash_func(),
                    length=32,
                    salt=salt,
                    iterations=self.key_iterations
                )
                return kdf.derive(ENCRYPTION_MASTER_KEY.encode())

            # Используем user_id вместо pseudonym_id для поиска в UserEncryptionKey
            user_id = pseudonym.user_id

            # Проверяем существование ключа
            user_key = self.session.query(UserEncryptionKey) \
                .filter_by(user_id=user_id) \
                .first()

            # Если ключ существует, используем его соль
            if user_key:
                salt = user_key.key_salt
            else:
                # Генерируем новую соль
                salt = os.urandom(16)

            # Выбираем хеш-алгоритм
            hash_func = {
                'SHA256': hashes.SHA256,
                'SHA512': hashes.SHA512
            }.get(self.hash_algorithm, hashes.SHA256)

            # Деривация ключа
            kdf = PBKDF2HMAC(
                algorithm=hash_func(),
                length=32,
                salt=salt,
                iterations=self.key_iterations
            )

            # Получаем ключ из мастер-ключа
            key = kdf.derive(ENCRYPTION_MASTER_KEY.encode())

            # Сохраняем ключ, если не существует
            if not user_key:
                key_hash = base64.urlsafe_b64encode(key).decode()
                new_key_record = UserEncryptionKey(
                    user_id=user_id,  # Здесь используем числовой user_id!
                    key_hash=key_hash,
                    key_salt=salt
                )
                self.session.add(new_key_record)
                self.session.commit()

            return key

        except Exception as e:
            logger.error(f"Error deriving encryption key: {e}")
            # Создаем резервный ключ в случае ошибки
            try:
                backup_salt = os.urandom(16)
                backup_kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=backup_salt,
                    iterations=100000
                )
                return backup_kdf.derive(ENCRYPTION_MASTER_KEY.encode())
            except Exception as backup_error:
                logger.critical(f"Failed to create backup key: {backup_error}")
                return None

    def encrypt_message(
            self,
            message: str,
            pseudonym_id: str
    ) -> Optional[str]:

        """
        Шифрование сообщения

        Args:
            message: Текст сообщения
            pseudonym_id: Псевдоним пользователя

        Returns:
            Зашифрованное сообщение или None
        """
        try:
            # Проверяем, включено ли шифрование
            if not self.encrypt_messages or not ENCRYPTION_MASTER_KEY:
                return message

            # Получаем ключ шифрования
            key = self._derive_encryption_key(pseudonym_id)
            if not key:
                return message

            # Создаем объект Fernet
            fernet = Fernet(base64.urlsafe_b64encode(key))

            # Шифруем сообщение
            encrypted_message = fernet.encrypt(message.encode()).decode()

            # Сохраняем зашифрованное сообщение
            content = DialogueContent(
                encrypted_content=encrypted_message.encode(),
                iv=fernet._encryption_key  # Вектор инициализации
            )
            self.session.add(content)

            # Создаем хеш сообщения правильным способом
            hash_obj = hashes.Hash(hashes.SHA256())
            hash_obj.update(message.encode())
            message_hash = base64.urlsafe_b64encode(hash_obj.finalize()).decode()

            # Создаем метаданные
            metadata = DialogueMetadata(
                pseudonym_id=pseudonym_id,
                role='user',
                message_hash=message_hash,
                content=content,
                timestamp=datetime.utcnow()
            )
            self.session.add(metadata)

            self.session.commit()

            return encrypted_message

        except Exception as e:
            logger.error(f"Error encrypting message: {e}")
            self.session.rollback()
            return message

    def decrypt_message(
            self,
            encrypted_message: str,
            pseudonym_id: str
    ) -> Optional[str]:
        """
        Расшифровка сообщения

        Args:
            encrypted_message: Зашифрованное сообщение
            pseudonym_id: Псевдоним пользователя

        Returns:
            Расшифрованное сообщение или None
        """
        try:
            # Проверяем, включено ли шифрование
            if not self.encrypt_messages or not ENCRYPTION_MASTER_KEY:
                return encrypted_message

            # Получаем ключ шифрования
            key = self._derive_encryption_key(pseudonym_id)
            if not key:
                return encrypted_message

            # Создаем объект Fernet
            fernet = Fernet(base64.urlsafe_b64encode(key))

            # Расшифровываем сообщение
            decrypted_message = fernet.decrypt(
                encrypted_message.encode()
            ).decode()

            return decrypted_message

        except Exception as e:
            logger.error(f"Error decrypting message: {e}")
            return encrypted_message

    def get_messages_by_pseudonym(
            self,
            pseudonym_id: str,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Получение сообщений для псевдонима с расшифровкой

        logging.info(f"ДИАГНОСТИКА: запрос сообщений для pseudonym_id={pseudonym_id}")

        Args:
            pseudonym_id: Псевдоним пользователя
            start_date: Начало периода (опционально)
            end_date: Конец периода (опционально)
            limit: Максимальное количество сообщений

        Returns:
            Список сообщений с ролями и содержимым
        """
        try:
            # Устанавливаем границы периода, если не указаны
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=30)
            if not end_date:
                end_date = datetime.utcnow()

            # Добавляем отладочную информацию
            logging.info(f"Getting messages for pseudonym {pseudonym_id}, limit: {limit}")

            # Запрос сообщений с метаданными
            messages_query = self.session.query(
                DialogueMetadata,
                DialogueContent
            ).join(
                DialogueContent,
                DialogueMetadata.content_id == DialogueContent.id
            ).filter(
                DialogueMetadata.pseudonym_id == pseudonym_id,
                DialogueMetadata.timestamp.between(start_date, end_date)
            ).order_by(
                DialogueMetadata.timestamp.desc()  # От новых к старым
            ).limit(limit)

            # Выполняем запрос и получаем результаты
            results = messages_query.all()
            logging.info(f"Found {len(results)} messages in database")

            # Обработка и расшифровка сообщений
            decrypted_messages = []
            for metadata, content in results:
                try:
                    # Проверяем формат содержимого
                    content_value = content.encrypted_content
                    if isinstance(content_value, bytes):
                        try:
                            # Пробуем декодировать байты в строку
                            content_value = content_value.decode('utf-8', errors='replace')
                        except Exception as decode_error:
                            logging.warning(f"Error decoding message content: {decode_error}")
                            # В случае ошибки оставляем как есть

                    # Расшифровываем содержимое при необходимости
                    decrypted_content = content_value
                    if self.encrypt_messages:
                        try:
                            decrypted_content = self.decrypt_message(
                                content_value,
                                pseudonym_id
                            )
                        except Exception as decrypt_error:
                            logging.error(f"Error decrypting message: {decrypt_error}")
                            # В случае ошибки расшифровки используем исходное содержимое
                            decrypted_content = f"[Ошибка расшифровки: {str(content_value)[:30]}...]"

                    # Добавляем сообщение в результат
                    decrypted_messages.append({
                        'role': metadata.role,  # Важно! Используем роль из метаданных
                        'content': decrypted_content,
                        'timestamp': metadata.timestamp.isoformat(),
                        'message_hash': metadata.message_hash
                    })

                    logging.debug(f"Processed message with role {metadata.role} from {metadata.timestamp}")

                except Exception as processing_error:
                    logging.error(f"Error processing message: {processing_error}")
                    # Пропускаем проблемные сообщения, но продолжаем обработку остальных

            logging.info(f"Returning {len(decrypted_messages)} processed messages")
            logging.info(f"ДИАГНОСТИКА: возвращаем {len(decrypted_messages)} сообщений")
            return decrypted_messages

        except Exception as e:
            logging.error(f"Error getting messages by pseudonym: {e}")
            return []

    def delete_messages(
            self,
            filter_params: Dict[str, Any]
    ) -> int:
        """
        Удаление сообщений с учетом фильтров

        Args:
            filter_params: Параметры фильтрации

        Returns:
            Количество удаленных сообщений
        """
        try:
            # Базовый запрос к метаданным
            query = self.session.query(DialogueMetadata)

            # Применяем фильтры
            if 'pseudonym_id' in filter_params:
                query = query.filter(
                    DialogueMetadata.pseudonym_id == filter_params['pseudonym_id']
                )

            if 'before_date' in filter_params:
                query = query.filter(
                    DialogueMetadata.timestamp < filter_params['before_date']
                )

            # Находим и удаляем связанные записи
            deleted_count = 0
            for metadata in query.all():
                # Удаляем связанный контент
                if metadata.content:
                    self.session.delete(metadata.content)

                # Удаляем метаданные
                self.session.delete(metadata)
                deleted_count += 1

            self.session.commit()
            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting messages: {e}")
            self.session.rollback()
            return 0
