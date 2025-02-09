# services/claude_service.py
import logging
from anthropic import Anthropic
from config.settings import (
    ANTHROPIC_API_KEY,
    SYSTEM_PROMPT,
    MAX_OUTPUT_TOKENS
)

logger = logging.getLogger(__name__)

class ClaudeService:
    def __init__(self):
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.conversations = {}  # Временное хранение истории диалогов

    def _get_conversation_history(self, user_id):
        """Получить историю диалога для пользователя"""
        return self.conversations.get(user_id, [])

    def _update_conversation_history(self, user_id, message):
        """Обновить историю диалога"""
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        self.conversations[user_id].append(message)

    def get_consultation(self, user_id: int, user_message: str) -> str:
        """Получить консультацию от Claude через Messages API"""
        try:
            conversation_history = self._get_conversation_history(user_id)

            # Формируем сообщения для API (без system prompt)
            messages = []

            # Добавляем историю диалога
            for msg in conversation_history:
                if msg["role"] != "system":  # Пропускаем системные сообщения из истории
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

            # Добавляем текущее сообщение пользователя
            messages.append({
                "role": "user",
                "content": user_message
            })

            # Отправляем запрос через Messages API
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                system=SYSTEM_PROMPT,  # Системный промпт передается отдельным параметром
                messages=messages,
                max_tokens=MAX_OUTPUT_TOKENS
            )

            # Получаем текст ответа
            response_text = response.content[0].text

            # Сохраняем сообщения в историю
            self._update_conversation_history(user_id,
                                           {"role": "user", "content": user_message})
            self._update_conversation_history(user_id,
                                           {"role": "assistant", "content": response_text})

            return response_text

        except Exception as e:
            logger.error(f"Error in Claude API call for user {user_id}: {e}")
            return "Извините, произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."

    def clear_conversation(self, user_id: int):
        """Очистить историю диалога для пользователя"""
        if user_id in self.conversations:
            del self.conversations[user_id]
