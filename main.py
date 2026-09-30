"""Точка входа приложения-напоминалки для Windows 10."""

import argparse

from db import DEFAULT_DB_PATH, Database
from gui import ReminderApp
from reminders import ReminderService


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Напоминалка для Windows 10")
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help="Путь к файлу базы данных SQLite3",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    db = Database(args.db)
    service = ReminderService(db)
    app = ReminderApp(service)
    try:
        app.mainloop()
    finally:
        db.close()


if __name__ == "__main__":
    main()
