# Kerosin White Lists Checker

Репозиторий собирает VLESS-ключи из семи источников, фильтрует неподходящие конфиги, проверяет TCP-доступность серверов и публикует две основные подписки:

- `good.txt` — полная подписка со всеми ключами, успешно прошедшими TCP-проверку
- `top50.txt` — подписка с 50 самыми стабильными ключами по истории успешных чеков

Для обратной совместимости `top15.txt` тоже сохраняется, но сейчас содержит тот же список, что и `top50.txt`.

Сайт в `docs/` показывает текущий `top50`, доступность, серию успешных прохождений и даёт варианты получения подписки через белые и прямые ссылки.

## Источники

- [igareck/vpn-configs-for-russia](https://github.com/igareck/vpn-configs-for-russia)
  - `WHITE-CIDR-RU-all.txt`
  - `Vless-Reality-White-Lists-Rus-Mobile.txt`
  - `Vless-Reality-White-Lists-Rus-Mobile-2.txt`
  - `WHITE-CIDR-RU-checked.txt`
- [FLEXIY0/matryoshka-vpn](https://github.com/FLEXIY0/matryoshka-vpn)
  - `configs/russia_whitelist.txt`
- [AvenCores/goida-vpn-configs](https://github.com/AvenCores/goida-vpn-configs)
  - `githubmirror/26.txt`
- [whoahaow/rjsxrd](https://github.com/whoahaow/rjsxrd)
  - `githubmirror/bypass/bypass-all.txt`

## Как работает

1. `check_and_save.py` загружает все семь списков.
2. Скрипт оставляет только `vless://`-строки, дедуплицирует их и нормализует имя: по первому emoji-флагу определяет страну и приводит хвост к формату `🇳🇱 The Netherlands`. Если флага нет, имя становится `Cosmos`.
3. Перед проверкой скрипт отбрасывает конфиги с `allowinsecure/insecure`, `security=none` и транспортом `xhttp`.
4. Скрипт делает TCP-подключение к уникальным `host:port` и переиспользует результат для конфигов, которые смотрят в один endpoint.
5. Результаты каждого запуска сохраняются в `history.json`, чтобы накапливать историю доступности.
6. Успешные ключи ранжируются по стабильности: availability, success streak и истории прохождения. Задержка используется только как вторичный tie-breaker.
7. Полный список сохраняется в `good.txt`, а `top50.txt` получает 50 самых стабильных ключей. `top15.txt` остаётся совместимым алиасом.
8. `docs/keys.json` обновляется для GitHub Pages.
9. GitHub Actions коммитит новые артефакты обратно в репозиторий.

## Автоматическое обновление

- Workflow `.github/workflows/check_keys.yml` запускается каждые 30 минут по `schedule` и вручную через `workflow_dispatch`.
- Из-за особенностей GitHub Actions scheduled workflow может запускаться с задержкой, а при высокой нагрузке отдельные окна могут быть пропущены.
- Чтобы уменьшить такие пропуски, cron смещён с начала часа на `17` и `47` минут каждого часа по UTC.

## Ограничения

- Это не полноценная VLESS-проверка, а именно TCP-check до `host:port`.
- Проверка выполняется с GitHub-hosted runners, поэтому задержки отличаются от реальных у пользователя.
- Поэтому `top50` строится не по минимальной задержке, а по стабильности прохождения серии чеков.

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

Основные подписки:

- [good.txt через jsDelivr](https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/good.txt)
- [top50.txt через jsDelivr](https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top50.txt)
- [top15.txt через jsDelivr](https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top15.txt)
- [good.txt через raw.githubusercontent.com](https://raw.githubusercontent.com/lilyungcykamane/vless-checker/refs/heads/main/good.txt)
- [top50.txt через raw.githubusercontent.com](https://raw.githubusercontent.com/lilyungcykamane/vless-checker/refs/heads/main/top50.txt)
- [top15.txt через raw.githubusercontent.com](https://raw.githubusercontent.com/lilyungcykamane/vless-checker/refs/heads/main/top15.txt)

На сайте кнопки подписки открывают модальное окно со способами выдачи:

- белая auto-update ссылка через jsDelivr
- ручная ссылка через Yandex Translate
- прямая ссылка через `raw.githubusercontent.com`

## Структура проекта

```text
vless-checker/
├── check_and_save.py    # Основной пайплайн генерации
├── checker.py           # Точка входа для локального запуска
├── stability_utils.py   # История чеков и рейтинг по стабильности
├── vless_utils.py       # Загрузка и нормализация ключей
├── history.json         # Накопленная история запусков
├── good.txt             # Полная подписка
├── top50.txt            # Топ-50 по стабильности
├── top15.txt            # Совместимый алиас top50
├── docs/
│   ├── index.html       # Сайт GitHub Pages
│   ├── script.js        # Рендер top50
│   ├── styles.css       # Стили сайта
│   └── keys.json        # Данные для фронта
└── .github/workflows/
    └── check_keys.yml   # Автоматическое обновление
```
