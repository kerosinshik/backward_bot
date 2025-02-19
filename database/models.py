# database/models.py
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

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

   user_id = Column(BigInteger, primary_key=True)
   current_context = Column(String(50))
   last_command = Column(String(50))
   updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserAction(Base):
   __tablename__ = 'user_actions'

   id = Column(Integer, primary_key=True)
   user_id = Column(BigInteger)
   action_type = Column(String(50))  # message, command, knowledge_view
   content = Column(Text, nullable=True)  # содержимое действия
   created_at = Column(DateTime, default=datetime.utcnow)


class ExerciseFeedback(Base):
   __tablename__ = 'exercise_feedback'

   id = Column(Integer, primary_key=True)
   user_id = Column(BigInteger)
   exercise_id = Column(String(50))
   exercise_date = Column(DateTime)
   feedback_date = Column(DateTime, default=datetime.utcnow)
   feedback_text = Column(Text)
   context = Column(Text)


class UserCredits(Base):
   """Модель для хранения кредитов пользователя"""
   __tablename__ = 'user_credits'

   user_id = Column(Integer, primary_key=True)
   credits_remaining = Column(Integer, default=0)
   has_used_trial = Column(Boolean, default=False)
   last_purchase_date = Column(DateTime, default=datetime.utcnow)
   created_at = Column(DateTime, default=datetime.utcnow)
   updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentHistory(Base):
   """Модель для хранения истории платежей"""
   __tablename__ = 'payment_history'

   id = Column(Integer, primary_key=True)
   user_id = Column(Integer, nullable=False)
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
   user_id = Column(Integer, nullable=False)
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




# Создание таблиц
def init_db(database_url):
   engine = create_engine(database_url)
   Base.metadata.create_all(engine)
   return engine

# Создание сессии
def get_session(engine):
   Session = sessionmaker(bind=engine)
   return Session()
