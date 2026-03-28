# Kerosin White Lists Checker

Репозиторий собирает VLESS-ключи из четырёх источников, проверяет TCP-доступность серверов и публикует два текстовых файла:

- `good.txt` — полная подписка со всеми ключами, успешно прошедшими TCP-проверку
- `top15.txt` — подписка с 15 самыми стабильными ключами по истории успешных чеков

Сайт в `docs/` показывает текущий `top15`, доступность, серию успешных прохождений и даёт кнопки подписки через jsDelivr.

## Источники

- `WHITE-CIDR-RU-all.txt`
- `Vless-Reality-White-Lists-Rus-Mobile.txt`
- `Vless-Reality-White-Lists-Rus-Mobile-2.txt`
- `WHITE-CIDR-RU-checked.txt`

Все списки берутся из репозитория [igareck/vpn-configs-for-russia](https://github.com/igareck/vpn-configs-for-russia).

## Как работает

1. `check_and_save.py` загружает все четыре списка.
2. Скрипт оставляет только `vless://`-строки, нормализует хвост после названия страны и дедуплицирует ключи.
3. Скрипт делает TCP-подключение к `host:port` каждого ключа и измеряет задержку.
4. Результаты каждого запуска сохраняются в `history.json`, чтобы накапливать историю доступности.
5. Успешные ключи ранжируются по стабильности: availability, success streak и истории прохождения. Задержка используется только как вторичный tie-breaker.
6. Полный список сохраняется в `good.txt`, а `top15.txt` получает 15 самых стабильных ключей.
7. `docs/keys.json` обновляется для GitHub Pages.
8. GitHub Actions коммитит новые артефакты обратно в репозиторий.

## Ограничения

- Это не полноценная VLESS-проверка, а именно TCP-check до `host:port`.
- Проверка выполняется с GitHub-hosted runners, поэтому задержки отличаются от реальных у пользователя.
- Поэтому `top15` строится не по минимальной задержке, а по стабильности прохождения серии чеков.

## Локальный запуск

```bash
git clone https://github.com/lilyungcykamane/vless-checker.git
cd vless-checker
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python3 check_and_save.py
```

## GitHub Pages

После включения Pages сайт будет доступен по адресу:
[lilyungcykamane.github.io/vless-checker](https://lilyungcykamane.github.io/vless-checker/)

Файлы подписок публикуются через jsDelivr:

- [good.txt](https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker@main/good.txt)
- [top15.txt](https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker@main/top15.txt)

## Структура проекта

```text
vless-checker/
├── check_and_save.py    # Основной пайплайн генерации
├── checker.py           # Точка входа для локального запуска
├── stability_utils.py   # История чеков и рейтинг по стабильности
├── vless_utils.py       # Загрузка и нормализация ключей
├── history.json         # Накопленная история запусков
├── good.txt             # Полная подписка
├── top15.txt            # Топ-15 по стабильности
├── docs/
│   ├── index.html       # Сайт GitHub Pages
│   ├── script.js        # Рендер top15
│   ├── styles.css       # Стили сайта
│   └── keys.json        # Данные для фронта
└── .github/workflows/
    └── check_keys.yml   # Автоматическое обновление
```
