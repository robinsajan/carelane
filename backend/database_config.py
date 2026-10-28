"""Choose one database for all application reads and writes at startup."""
from collections.abc import Mapping


def use_local_database(environment: Mapping[str, str]) -> bool:
    value = environment.get('local_db', environment.get('LOCAL_DB', 'False')).strip().lower()
    if value not in ('true', 'false'):
        raise RuntimeError('local_db must be True or False.')
    return value == 'true'


def database_url(local_db: bool, environment: Mapping[str, str]) -> str:
    if local_db:
        return ''  # Ignore Neon credentials in local mode.
    url = environment.get('DATABASE_URL', '').strip()
    if not url:
        raise RuntimeError('DATABASE_URL is required when local_db=False. Set local_db=True to use SQLite.')
    if not url.startswith(('postgresql://', 'postgres://')):
        raise RuntimeError('DATABASE_URL must be a PostgreSQL connection URL.')
    return url
