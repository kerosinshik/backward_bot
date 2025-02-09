from setuptools import setup, find_packages

setup(
    name="backward_bot",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'python-telegram-bot==20.7',
        'anthropic==0.45.0',
        'SQLAlchemy==2.0.25',
        'python-dotenv==1.0.0',
        'aiohttp==3.9.1',
        'cryptography==41.0.7',
        'alembic==1.13.1',
        'psycopg2-binary==2.9.9',
        'python-jose==3.3.0',
        'httpx==0.25.2',
        'pytz'
    ],
)
