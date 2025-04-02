# database/models.py
from sqlalchemy import Index, create_engine, Column, Integer, BIGINT, Float, String, Text, ForeignKey, DateTime, Boolean, \
    LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid

Base = declarative_base()


class KnowledgeItem(Base):
    __tablename__ = 'knowledge_items'

    id = Column(Integer, primary_key=True)
    category = Column(String(50))
    title = Column(String(200))
    content = Column(Text)
    command = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserState(Base):
    __tablename__ = 'user_states'

    user_id = Column(BIGINT, primary_key=True)
    current_context = Column(String(50))
    last_command = Column(String(50))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserAction(Base):
    __tablename__ = 'user_actions'

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT)
    action_type = Column(String(50))  # message, command, knowledge_view
    content = Column(Text, nullable=True)  # содержимое действия
    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = 'feedback'

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT)
    feedback_type = Column(String(50))  # 'general', 'consultation', etc.
    feedback_date = Column(DateTime, default=datetime.utcnow)
    feedback_text = Column(Text)
    context = Column(Text, nullable=True)  # Опциональный контекст


class UserCredits(Base):
    """Модель для хранения кредитов пользователя"""
    __tablename__ = 'user_credits'

    user_id = Column(BIGINT, primary_key=True)
    credits_remaining = Column(Integer, default=0)
    has_used_trial = Column(Boolean, default=False)
    last_purchase_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentHistory(Base):
    """Модель для хранения истории платежей"""
    __tablename__ = 'payment_history'

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT, nullable=False)
    payment_id = Column(String(50), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    plan_id = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)  # pending, succeeded, canceled, error
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSubscription(Base):
    """Модель для хранения подписок пользователей"""
    __tablename__ = 'user_subscriptions'

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT, nullable=False)
    plan_id = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)  # active, expired, canceled
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def is_active(self):
        """Проверяет, активна ли подписка"""
        now = datetime.utcnow()
        return (
                self.status == 'active' and
                self.start_date <= now and
                (self.end_date is None or self.end_date > now)
        )


# Таблицы промокодов

class PromoCode(Base):
    """Модель для хранения промокодов"""
    __tablename__ = 'promo_codes'

    code = Column(String(50), primary_key=True)
    credits = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    max_uses = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0)
    created_by = Column(BIGINT, nullable=True)  # ID администратора, создавшего промокод
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Дата истечения промокода

    def __repr__(self):
        return f"<PromoCode(code='{self.code}', credits={self.credits}, active={self.is_active})>"


class PromoCodeUsage(Base):
    """Модель для отслеживания использования промокодов"""
    __tablename__ = 'promo_code_usage'

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT, nullable=False, index=True)
    promo_code = Column(String(50), ForeignKey('promo_codes.code'), nullable=False)
    credits_granted = Column(Integer, nullable=False)
    activated_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<PromoCodeUsage(user={self.user_id}, code='{self.promo_code}', credits={self.credits_granted})>"



# НОВЫЕ МОДЕЛИ ДЛЯ КОНФИДЕНЦИАЛЬНОСТИ

class UserPseudonym(Base):
    """Модель для псевдонимизации пользователей"""
    __tablename__ = 'user_pseudonyms'

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT, nullable=True)
    pseudonym_id = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserEncryptionKey(Base):
    """Модель для хранения ключей шифрования пользователей"""
    __tablename__ = 'user_encryption_keys'

    id = Column(Integer, primary_key=True)
    user_id = Column(BIGINT, unique=True, nullable=False)
    key_hash = Column(String(128), nullable=False)  # Хеш ключа для проверки целостности
    key_salt = Column(LargeBinary, nullable=False)  # Соль для производного ключа
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Реальный ключ шифрования не хранится в базе данных


class DialogueMetadata(Base):
    """Модель для хранения метаданных диалогов (отдельно от контента)"""
    __tablename__ = 'dialogue_metadata'

    id = Column(Integer, primary_key=True)
    pseudonym_id = Column(String(36), index=True, nullable=False)  # Используем псевдоним вместо user_id
    role = Column(String(20), nullable=False)  # 'user' или 'assistant'
    message_hash = Column(String(64), nullable=False)  # Хеш сообщения для проверки целостности
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)

    # Внешний ключ на содержимое сообщения
    content_id = Column(Integer, ForeignKey('dialogue_content.id', ondelete='CASCADE'))
    content = relationship("DialogueContent", back_populates="message_metadata")


class DialogueContent(Base):
    """Модель для хранения зашифрованного содержимого сообщений"""
    __tablename__ = 'dialogue_content'

    id = Column(Integer, primary_key=True)
    encrypted_content = Column(LargeBinary, nullable=False)  # Зашифрованный текст
    iv = Column(LargeBinary, nullable=False)  # Вектор инициализации для AES
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связь с метаданными (один-к-одному)
    message_metadata = relationship("DialogueMetadata", back_populates="content", uselist=False)


class DataRetentionLog(Base):
    """Модель для логирования удаления данных"""
    __tablename__ = 'data_retention_logs'

    id = Column(Integer, primary_key=True)
    pseudonym_id = Column(String(36), index=True, nullable=False)
    operation_type = Column(String(20), nullable=False)  # 'cleanup', 'user_request', 'expiration'
    records_affected = Column(Integer, default=0)
    date_range_start = Column(DateTime, nullable=True)
    date_range_end = Column(DateTime, nullable=True)
    operation_date = Column(DateTime, default=datetime.utcnow)
    reason = Column(String(200), nullable=True)


class ErrorLog(Base):
    """
    Модель для хранения логов ошибок с учетом конфиденциальности
    """
    __tablename__ = 'error_logs'

    id = Column(Integer, primary_key=True)

    # Псевдонимизированный идентификатор пользователя
    pseudonym_id = Column(String(36), nullable=True, index=True)

    # Оригинальный user_id (опционально, с возможностью nullability)
    user_id = Column(BIGINT, nullable=True, index=True)

    # Тип ошибки для категоризации
    error_type = Column(String(50), nullable=False, index=True)

    # Зашифрованные или обезличенные детали ошибки
    error_details = Column(Text, nullable=False)

    # Временная метка создания
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Индекс для быстрого поиска
    __table_args__ = (
        Index('idx_error_logs_pseudonym_type', 'pseudonym_id', 'error_type'),
        Index('idx_error_logs_created_at', 'created_at')
    )

    def __repr__(self):
        """
        Строковое представление лога ошибки
        """
        return (
            f"<ErrorLog(id={self.id}, "
            f"type={self.error_type}, "
            f"pseudonym_id={self.pseudonym_id}, "
            f"created_at={self.created_at})>"
        )


# Функции для инициализации базы данных
def init_db(database_url):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


# Создание сессии
def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
