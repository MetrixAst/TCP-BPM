"""
Управление подключёнными BPM-серверами.

    python -m gateway.cli add "ТРЦ Мега" https://bpm.mega.kz   # выдаёт API-ключ для .env BPM
    python -m gateway.cli list
    python -m gateway.cli disable https://bpm.mega.kz
    python -m gateway.cli enable https://bpm.mega.kz
"""

import argparse
import os

from .store import Store


def main(argv=None):
    parser = argparse.ArgumentParser(prog='gateway.cli')
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add', help='подключить BPM-сервер')
    add.add_argument('name')
    add.add_argument('base_url')
    sub.add_parser('list', help='список серверов')
    for name in ('disable', 'enable'):
        cmd = sub.add_parser(name)
        cmd.add_argument('base_url')
    args = parser.parse_args(argv)

    store = Store(os.environ.get('GATEWAY_DB_PATH', 'gateway.sqlite3'))
    if args.command == 'add':
        key = store.add_backend(args.name, args.base_url)
        print(f'Сервер подключён. В .env этого BPM пропишите:\nAUTH_GATEWAY_API_KEY={key}')
    elif args.command == 'list':
        for row in store.list_backends():
            state = 'вкл' if row['is_active'] else 'выкл'
            print(f"{row['id']:>3}  {state:4}  {row['logins']:>6} логинов  {row['base_url']}  {row['name']}"
                  f"  (обновлено {row['logins_synced_at'] or '—'})")
    else:
        found = store.set_active(args.base_url, args.command == 'enable')
        print('Готово' if found else 'Сервер не найден')


if __name__ == '__main__':
    main()
