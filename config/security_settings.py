# Расширенные настройки безопасности бота

import os
from datetime import timedelta

# Политика паролей и аутентификации
PASSWORD_POLICY = {
    'min_length': 12,
    'require_uppercase': True,
    'require_lowercase': True,
    'require_digits': True,
    'require_special_chars': True,
    'max_login_attempts': 5,
    'lockout_duration': timedelta(minutes=15)
}

# Настройки двухфакторной аутентификации
TWO_FACTOR_AUTH = {
    'enabled': os.getenv('TWO_FACTOR_AUTH_ENABLED', 'False').lower() == 'true',
    'method': os.getenv('TWO_FACTOR_METHOD', 'telegram'),  # telegram, email, app
    'backup_codes_count': 5,
    'backup_codes_length': 8,
    'backup_codes_validity': timedelta(days=30)
}

# Настройки JWT-токенов
JWT_SETTINGS = {
    'secret_key': os.getenv('JWT_SECRET_KEY', os.urandom(32)),
    'algorithm': 'HS256',
    'access_token_expire_minutes': 15,
    'refresh_token_expire_days': 30
}

# Политика аудита безопасности
SECURITY_AUDIT = {
    'log_sensitive_actions': True,
    'sensitive_actions': [
        'login_attempt',
        'password_change',
        'account_creation',
        'account_deletion',
        'payment',
        'data_export'
    ],
    'retention_days': 365,  # Хранение журналов аудита
    'alert_threshold': {
        'failed_logins': 3,  # Количество неудачных попыток входа
        'unusual_activity': 5  # Количество необычных действий
    }
}

# Политика обработки уязвимостей
VULNERABILITY_POLICY = {
    'scan_frequency': timedelta(days=7),  # Периодичность сканирования
    'auto_update': {
        'enabled': True,
        'check_interval': timedelta(days=1)
    },
    'critical_vulnerability_response': 'immediate_shutdown',  # immediate_shutdown, restricted_mode
    'notification_emails': os.getenv('SECURITY_NOTIFICATION_EMAILS', '').split(',')
}

# Настройки защиты от брутфорса
BRUTE_FORCE_PROTECTION = {
    'enabled': True,
    'max_attempts': 5,
    'block_duration': timedelta(minutes=15),
    'tracking_period': timedelta(hours=1)
}

# Настройки криптографии
CRYPTOGRAPHY_SETTINGS = {
    'encryption_algorithms': ['AES-256-GCM', 'ChaCha20-Poly1305'],
    'preferred_algorithm': 'AES-256-GCM',
    'key_rotation_period': timedelta(days=90),
    'key_derivation_iterations': 100000,
    'salt_length': 16  # Длина соли в байтах
}

# Политика управления сессиями
SESSION_MANAGEMENT = {
    'max_concurrent_sessions': 3,
    'session_timeout': timedelta(hours=2),
    'idle_timeout': timedelta(minutes=30),
    'remember_me_duration': timedelta(days=30)
}

# Настройки защиты от CSRF
CSRF_PROTECTION = {
    'enabled': True,
    'token_lifetime': timedelta(hours=1),
    'exclude_routes': [
        '/health',
        '/metrics'
    ]
}

# Настройки логирования безопасности
SECURITY_LOGGING = {
    'log_level': 'INFO',
    'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'sensitive_data_masking': True,
    'mask_patterns': [
        r'\b\d{16}\b',  # Номера карт
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        r'\b\d{3}-\d{2}-\d{4}\b'  # SSN
    ]
}

# Политика обработки персональных данных
PERSONAL_DATA_POLICY = {
    'minimize_collection': True,
    'purpose_limitation': True,
    'consent_required': True,
    'data_anonymization': {
        'enabled': True,
        'methods': ['hashing', 'pseudonymization']
    },
    'data_portability': {
        'enabled': True,
        'formats': ['json', 'csv']
    }
}

# Настройки безопасности API
API_SECURITY = {
    'rate_limiting': {
        'max_requests_per_minute': 100,
        'max_requests_per_hour': 1000
    },
    'allowed_origins': [
        'https://t.me',
        'http://localhost:3000'  # Для локальной разработки
    ],
    'cors_enabled': True
}
