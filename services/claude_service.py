# services/claude_service.py
import anthropic
from config import settings
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from database.models import UserAction, DialogueMetadata, DialogueContent
from services.encryption_service import EncryptionService


class ClaudeService:
    def __init__(self, session: Session):
        self.session = session
        self.encryption_service = EncryptionService(session)
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.max_tokens = settings.MAX_OUTPUT_TOKENS
        self.max_context_messages = settings.DIALOGUE_SETTINGS.get('max_context_messages', 30)
        self.max_tokens_per_context = settings.DIALOGUE_SETTINGS.get('max_tokens_per_context', 4000)

    def get_consultation(self, user_id: int, user_message: str) -> str:
        try:
            # Проверяем длину сообщения
            if len(user_message) > settings.MAX_INPUT_CHARS:
                self._log_action(user_id, "error", "Message too long")
                return f"Пожалуйста, сократите сообщение до {settings.MAX_INPUT_CHARS} символов."

            # Получаем pseudonym_id
            pseudonym_id = self.encryption_service.ensure_pseudonym(user_id)

            # Получаем контекст диалога
            context_messages = self.encryption_service.get_messages_by_pseudonym(
                pseudonym_id,
                limit=self.max_context_messages
            )

            # Создаем пустой список, если context_messages равен None
            if context_messages is None:
                context_messages = []
                logging.warning(f"Context messages is None for user {user_id}, using empty list")

            # ВАЖНОЕ ИСПРАВЛЕНИЕ: меняем порядок сообщений на хронологический
            # Так как они по умолчанию отсортированы от новых к старым
            context_messages.reverse()

            # Добавляем лог для отладки
            logging.info(f"Retrieved {len(context_messages)} context messages for user {user_id}")
            logging.info(f"Context messages: {context_messages}")

            # Подготавливаем сообщения для Claude
            claude_messages = []

            # Добавляем контекст диалога
            for msg in context_messages:
                claude_messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })

            # Добавляем текущее сообщение пользователя
            claude_messages.append({"role": "user", "content": user_message})

            # Отправляем запрос в Claude с динамическими параметрами
            try:
                # Добавляем отладочные сообщения
                logging.info("=== DEBUG: Starting Claude API request ===")
                logging.info(f"Using model: {getattr(settings, 'CLAUDE_MODEL', 'claude-3-haiku-20240307')}")
                logging.info(f"System prompt length: {len(settings.SYSTEM_PROMPT)}")
                logging.info(f"Thinking enabled: {getattr(settings, 'CLAUDE_THINKING_ENABLED', False)}")
                logging.info(f"Temperature: {getattr(settings, 'CLAUDE_TEMPERATURE', 'not set')}")
                logging.info(f"Top P: {getattr(settings, 'CLAUDE_TOP_P', 'not set')}")
                logging.info(f"Max tokens: {self.max_tokens}")

                # Создаем словарь параметров API
                api_params = {
                    "model": getattr(settings, 'CLAUDE_MODEL', "claude-3-haiku-20240307"),
                    "system": settings.SYSTEM_PROMPT,
                    "messages": claude_messages,
                    "max_tokens": self.max_tokens
                }

                # Добавляем дополнительные параметры
                if hasattr(settings, 'CLAUDE_TEMPERATURE'):
                    api_params["temperature"] = settings.CLAUDE_TEMPERATURE
                if hasattr(settings, 'CLAUDE_TOP_P'):
                    api_params["top_p"] = settings.CLAUDE_TOP_P

                # Включаем режим thinking, если он включен
                thinking_enabled = getattr(settings, 'CLAUDE_THINKING_ENABLED', False)
                if thinking_enabled:
                    api_params["anthropic_metadata"] = {"thinking": True}

                # Логируем итоговые параметры запроса (без содержимого сообщений)
                log_params = api_params.copy()
                log_params["messages"] = f"[{len(claude_messages)} messages]"
                logging.info(f"API parameters: {log_params}")

                # Вызываем API
                response = self.client.messages.create(**api_params)

            except Exception as api_error:
                error_details = str(api_error)
                logging.error(f"Claude API error for user {user_id}: {error_details}")
                self._log_action(user_id, "api_error", error_details[:200])
                return self._handle_api_error(error_details)

            # Проверяем, что ответ содержит контент
            if not response or not hasattr(response, 'content') or not response.content:
                self._log_action(user_id, "error", "Empty API response")
                return "Не удалось получить ответ. Пожалуйста, попробуйте еще раз."

            # Извлекаем текст из ответа
            if len(response.content) > 0 and hasattr(response.content[0], 'text'):
                response_text = response.content[0].text
            else:
                self._log_action(user_id, "error", "Invalid response format")
                return "Получен некорректный формат ответа. Пожалуйста, попробуйте еще раз."

            # Проверяем длину ответа
            if len(response_text) > settings.MAX_OUTPUT_CHARS:
                response_text = response_text[:settings.MAX_OUTPUT_CHARS] + "..."

            # Шифруем и сохраняем сообщения пользователя и бота
            self._save_dialogue_messages(pseudonym_id, user_message, response_text)

            # Логируем действие в БД
            self._log_action(user_id, "consultation", len(response_text))

            return response_text

        except Exception as unexpected_error:
            logging.error(f"Unexpected error in Claude consultation: {unexpected_error}")
            self._log_action(user_id, "unexpected_error", str(unexpected_error)[:100])
            return "Извините, произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."

        
    def _save_dialogue_messages(self, pseudonym_id: str, user_message: str, bot_response: str):
        """Сохранение диалога с шифрованием и правильными ролями"""
        try:
            logging.info(f"Saving dialogue messages for pseudonym {pseudonym_id}")

            # 1. Сохраняем сообщение пользователя с ролью 'user'
            user_content_str = user_message
            if settings.DIALOGUE_SETTINGS.get('encrypt_messages', True):
                user_content_str = self.encryption_service.encrypt_message(user_message, pseudonym_id)

            user_content = DialogueContent(
                encrypted_content=user_content_str.encode() if isinstance(user_content_str, str) else user_content_str,
                iv=b'placeholder',  # Используйте реальный вектор инициализации при необходимости
                created_at=datetime.utcnow()
            )
            self.session.add(user_content)
            self.session.flush()  # Чтобы получить ID содержимого

            user_metadata = DialogueMetadata(
                pseudonym_id=pseudonym_id,
                role='user',  # Важно! Правильная роль для сообщения пользователя
                message_hash='hash_placeholder',  # Заменить на реальный хеш при необходимости
                content_id=user_content.id,
                timestamp=datetime.utcnow()
            )
            self.session.add(user_metadata)

            # 2. Сохраняем ответ бота с ролью 'assistant'
            bot_content_str = bot_response
            if settings.DIALOGUE_SETTINGS.get('encrypt_messages', True):
                bot_content_str = self.encryption_service.encrypt_message(bot_response, pseudonym_id)

            bot_content = DialogueContent(
                encrypted_content=bot_content_str.encode() if isinstance(bot_content_str, str) else bot_content_str,
                iv=b'placeholder',  # Используйте реальный вектор инициализации при необходимости
                created_at=datetime.utcnow()
            )
            self.session.add(bot_content)
            self.session.flush()  # Чтобы получить ID содержимого

            bot_metadata = DialogueMetadata(
                pseudonym_id=pseudonym_id,
                role='assistant',  # Важно! Правильная роль для ответа бота
                message_hash='hash_placeholder',  # Заменить на реальный хеш при необходимости
                content_id=bot_content.id,
                timestamp=datetime.utcnow()
            )
            self.session.add(bot_metadata)

            # Фиксируем все изменения в БД
            self.session.commit()
            logging.info(f"Successfully saved user message and bot response with correct roles")

        except Exception as e:
            logging.error(f"Error in _save_dialogue_messages: {e}")
            self.session.rollback()

    def _log_action(self, user_id: int, action_type: str, content=None):
        """Простое логирование действий в БД"""
        try:
            action = UserAction(
                user_id=user_id,
                action_type=action_type,
                content=str(content) if content is not None else None,
                created_at=datetime.utcnow()
            )
            self.session.add(action)
            self.session.commit()
        except Exception as e:
            logging.error(f"Error logging action: {e}")
            self.session.rollback()

    def _handle_api_error(self, error_details):
        """Обработка ошибок API с информативными сообщениями"""
        if "rate limit" in error_details.lower():
            return "Извините, превышен лимит запросов. Пожалуйста, подождите немного и попробуйте снова."
        elif "internal server error" in error_details.lower():
            return "Технические неполадки на стороне сервиса. Пожалуйста, попробуйте позже."
        else:
            return "Произошла непредвиденная ошибка при обработке запроса. Приносим извинения."

    def clear_conversation(self, user_id: int):
        """Очистка контекста диалога"""
        try:
            # Получаем pseudonym_id
            pseudonym_id = self.encryption_service.ensure_pseudonym(user_id)

            # Находим и удаляем старые сообщения
            cutoff_date = datetime.utcnow() - timedelta(
                days=settings.DIALOGUE_SETTINGS.get('context_retention_days', 90)
            )

            deleted_count = self.encryption_service.delete_messages({
                'pseudonym_id': pseudonym_id,
                'before_date': cutoff_date
            })

            self._log_action(user_id, "conversation_reset", f"Deleted {deleted_count} messages")
            return True
        except Exception as e:
            logging.error(f"Error clearing conversation: {e}")
            return False
