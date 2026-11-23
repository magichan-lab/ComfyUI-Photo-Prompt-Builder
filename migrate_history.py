"""Manually run the same idempotent migration performed on first database access."""
import argparse
from pathlib import Path

import history


def main():
    parser = argparse.ArgumentParser(description='Migrate prompt history JSON to SQLite (source is preserved).')
    parser.add_argument('--source', type=Path, help='Legacy JSON path (defaults to data/prompt_history.json)')
    parser.add_argument('--database', type=Path, help='Destination SQLite path (defaults to data/prompt_history.sqlite3)')
    args = parser.parse_args()
    if args.source is not None:
        if not args.source.is_file():
            parser.error(f'Source does not exist: {args.source}')
        history.FILE = args.source
    if args.database is not None:
        history.DB_FILE = args.database
    if history.FILE.resolve() == history.DB_FILE.resolve():
        parser.error('Source and database must be different files')
    try:
        print(f'SQLite history ready: {history.migrate()} (existing databases are preserved)')
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f'Migration failed: {exc}\n')


if __name__ == '__main__':
    main()
