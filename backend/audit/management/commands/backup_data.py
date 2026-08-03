import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Back up the SQLite database (and, if any, uploaded media files) to a timestamped '
        'folder under backend/backups/. Nothing in this project runs on a schedule by '
        'itself -- point your OS scheduler at this command to run it daily, e.g.:\n'
        '  Windows Task Scheduler: program venv\\Scripts\\python.exe, '
        'arguments "manage.py backup_data", start in backend/\n'
        '  cron: 0 2 * * * /path/to/venv/bin/python /path/to/backend/manage.py backup_data'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=14,
            help='Number of most recent backups to keep; older ones are deleted. Default 14.',
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES['default']['NAME'])
        if not db_path.exists():
            self.stderr.write(f'No database found at {db_path} - nothing to back up.')
            return

        backups_dir = Path(settings.BASE_DIR) / 'backups'
        backups_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        db_backup_path = backups_dir / f'db_{timestamp}.sqlite3'
        self._backup_sqlite(db_path, db_backup_path)
        self.stdout.write(self.style.SUCCESS(f'Database backed up to {db_backup_path}'))

        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists() and any(media_root.iterdir()):
            archive_base = backups_dir / f'media_{timestamp}'
            archive_path = shutil.make_archive(str(archive_base), 'zip', root_dir=str(media_root))
            self.stdout.write(self.style.SUCCESS(f'Media files backed up to {archive_path}'))

        keep = options['keep']
        self._prune(backups_dir, 'db_*.sqlite3', keep)
        self._prune(backups_dir, 'media_*.zip', keep)

    def _backup_sqlite(self, db_path, backup_path):
        # SQLite's own backup API rather than a raw file copy -- safe even while the
        # live dev server has the database open (handles an in-progress write/WAL
        # correctly), unlike copying the file directly which could capture a
        # half-written state.
        source = sqlite3.connect(str(db_path))
        dest = sqlite3.connect(str(backup_path))
        try:
            with dest:
                source.backup(dest)
        finally:
            source.close()
            dest.close()

    def _prune(self, backups_dir, pattern, keep):
        files = sorted(backups_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            old.unlink()
            self.stdout.write(f'Removed old backup: {old.name}')
