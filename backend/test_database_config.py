"""Database selection checks never connect to the hospital's Neon database."""
import sqlite3
from unittest.mock import patch

import pytest

from backend.database_config import database_url, use_local_database


def test_local_mode_ignores_neon_configuration():
    environment = {'local_db': 'True', 'DATABASE_URL': 'not-a-valid-neon-url'}
    assert use_local_database(environment) is True
    assert database_url(True, environment) == ''


def test_neon_mode_requires_valid_url():
    assert use_local_database({}) is False
    assert use_local_database({'local_db': 'False'}) is False
    url = 'postgresql://example.invalid/hospital'
    assert database_url(False, {'DATABASE_URL': url}) == url
    for environment in ({}, {'DATABASE_URL': 'sqlite:///test.db'}):
        with pytest.raises(RuntimeError):
            database_url(False, environment)


def test_switch_validation():
    assert use_local_database({'LOCAL_DB': 'TRUE'}) is True
    assert use_local_database({'local_db': ' false '}) is False
    with pytest.raises(RuntimeError, match='True or False'):
        use_local_database({'local_db': 'maybe'})


def test_local_connection_persists_writes_without_contacting_neon(tmp_path, monkeypatch):
    monkeypatch.setenv('local_db', 'True')
    from backend import main as m
    path = tmp_path / 'local.sqlite3'
    monkeypatch.setattr(m, 'DATABASE_URL', database_url(True, {'DATABASE_URL': 'postgresql://example.invalid/hospital'}))
    monkeypatch.setattr(m, 'DB_PATH', path)
    with patch.object(m.postgres, 'connect', side_effect=AssertionError('Neon must not be contacted')):
        with m.connect() as db:
            db.execute('CREATE TABLE sample (value TEXT)')
            db.execute('INSERT INTO sample VALUES (?)', ('before',))
        with m.connect() as db:
            db.execute('UPDATE sample SET value=?', ('after',))
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT value FROM sample').fetchone()[0] == 'after'


def test_neon_connection_uses_selected_url_and_schema(monkeypatch):
    monkeypatch.setenv('local_db', 'True')
    from backend import main as m
    url = database_url(False, {'DATABASE_URL': 'postgresql://example.invalid/hospital'})
    monkeypatch.setattr(m, 'DATABASE_URL', url)
    monkeypatch.setattr(m, 'DATABASE_SCHEMA', 'test_schema')
    with patch.object(m.postgres, 'connect') as connect:
        assert m.connect() is connect.return_value
        connect.assert_called_once_with(url, 'test_schema')
