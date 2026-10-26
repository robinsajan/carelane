"""Local maintenance commands; no maintenance endpoints are exposed over HTTP."""
import argparse
import getpass
import os
import sqlite3
from pathlib import Path

if __package__:
    from . import main as m
else:
    import main as m


def main():
    parser = argparse.ArgumentParser(description='Hospital OPD local maintenance')
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('init', help='Initialize the local database and first-run setup key')
    backup = subs.add_parser('backup', help='Create a consistent SQLite backup, including active WAL data')
    backup.add_argument('destination', type=Path)
    verify = subs.add_parser('verify-backup', help='Verify integrity, foreign keys and schema of a backup')
    verify.add_argument('source', type=Path)
    restore = subs.add_parser('restore-copy', help='Restore a backup to a NEW database path; never overwrite live data')
    restore.add_argument('source', type=Path)
    restore.add_argument('destination', type=Path)
    subs.add_parser('recover-master', help='Local server operator only: reset the sole Master password interactively')
    args = parser.parse_args()
    if m.DATABASE_URL and args.command == 'backup':
        parser.error('Neon uses PostgreSQL backups. Use pg_dump or the Neon backup/restore tools; SQLite backup is only available in offline mode.')
    if args.command == 'init':
        m.init_db()
        print('Database initialized: Neon PostgreSQL' if m.DATABASE_URL else f'Database initialized: {m.DB_PATH}')
        print(f'First-run setup key location: {m.SETUP_PATH}')
    elif args.command == 'backup':
        if not m.DB_PATH.exists():
            parser.error('Database does not exist.')
        if args.destination.exists():
            parser.error('Destination already exists; choose a new filename.')
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        with m.connect() as source, sqlite3.connect(args.destination) as dest:
            source.backup(dest)
        verify_backup(args.destination)
        print(f'Backup created and verified: {args.destination.resolve()}')
    elif args.command == 'verify-backup':
        verify_backup(args.source)
        print('Backup integrity, foreign keys and schema verified.')
    elif args.command == 'restore-copy':
        verify_backup(args.source)
        if args.destination.exists() or args.destination.resolve() == m.DB_PATH.resolve():
            parser.error('Destination must be a new path, separate from the live database.')
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(f'file:{args.source.resolve().as_posix()}?mode=ro', uri=True) as source, sqlite3.connect(args.destination) as dest:
            source.backup(dest)
        verify_backup(args.destination)
        print(f'Restored and verified a separate database copy: {args.destination.resolve()}')
        print('Stop the application, then set OPD_DATABASE to this path to use the restored copy.')
    elif args.command == 'recover-master':
        if not m.DATABASE_URL and not m.DB_PATH.exists():
            parser.error('Database does not exist.')
        print('Run this locally on the hospital server while the application is stopped.')
        if input('Type RECOVER to reset the existing Master credentials: ') != 'RECOVER':
            return
        password = getpass.getpass('New Master password (12+ characters, uppercase, number, symbol): ')
        error = m.password_policy_error(password)
        if error:
            parser.error(error)
        if password != getpass.getpass('Confirm new password: '):
            parser.error('Passwords must match.')
        with m.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            user = db.execute("SELECT * FROM users WHERE role='Master'").fetchone()
            if not user:
                parser.error('Complete first-run setup instead.')
            db.execute('UPDATE users SET password=?,must_change=0,version=version+1 WHERE id=?', (m.password_hash(password), user['id']))
            db.execute('DELETE FROM sessions')
            db.execute('DELETE FROM login_attempts')
            m.audit(db, user, 'Local Master recovery', 'user', user['id'], 'Server operator recovered credentials; all sessions revoked')
        print('Existing Master recovered. No new Master account was created. All sessions were revoked.')


def verify_backup(path):
    if not path.is_file():
        raise SystemExit('Backup file does not exist.')
    with sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('Backup integrity check failed.')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Backup contains broken foreign keys.')
        version = db.execute('SELECT version FROM schema_version').fetchone()[0]
        if version != 1:
            raise SystemExit('Unsupported database schema version.')


if __name__ == '__main__':
    main()
