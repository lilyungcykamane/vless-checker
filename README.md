# Kerosin White Lists Checker

Репозиторий собирает `vless://`-ключи из основного набора whitelist-источников, отбрасывает неподдерживаемые варианты, прогоняет кандидаты через `TCP` precheck и затем проверяет их через `sing-box`, публикуя два текстовых файла:

- `good.txt` — полная подписка со всеми ключами, успешно прошедшими `TCP + sing-box` проверку
- `top15.txt` — подписка с 15 самыми стабильными ключами по истории успешных чеков

Сайт в `docs/` показывает текущий `top15`, доступность, серию успешных прохождений и даёт варианты получения подписки через белые и прямые ссылки.

## Источники

- Активный список источников описан в `vless_utils.py`.
- Сейчас используются 4 базовых списка из `igareck/vpn-configs-for-russia` и 2 дополнительных источника:
  - `whoahaow/rjsxrd` → `githubmirror/bypass/bypass-all.txt`
  - `AvenCores/goida-vpn-configs` → `githubmirror/26.txt`
- Остальные кандидаты из предыдущего расширения не удалены, а закомментированы рядом в коде.

## Как работает

1. `check_and_save.py` загружает все доступные источники из каталога.
2. Скрипт оставляет только `vless://`-строки, нормализует хвост после названия страны и дедуплицирует ключи.
3. Перед сетевой проверкой отбрасываются ключи с `type=xhttp`, `security=none` и прочими неподдерживаемыми transport/security-комбинациями.
4. Скрипт делает быстрый `TCP connect` к `host:port` каждого кандидата и измеряет задержку.
5. Только ключи, прошедшие `TCP`, проверяются через локально поднятый `sing-box` и `GET https://www.gstatic.com/generate_204` через `SOCKS5`.
6. Результаты каждого запуска сохраняются в `history.json`, чтобы накапливать историю доступности.
7. Успешные ключи ранжируются по стабильности: availability, success streak и истории прохождения. Задержка используется только как вторичный tie-breaker.
8. Полный список сохраняется в `good.txt`, а `top15.txt` получает 15 самых стабильных ключей.
9. `docs/keys.json` обновляется для GitHub Pages.
10. Ошибка отдельного источника не останавливает весь запуск: он попадает в статистику как недоступный, а остальные списки продолжают обрабатываться.
11. GitHub Actions коммитит новые артефакты обратно в репозиторий.

## Автоматическое обновление

- Workflow `.github/workflows/check_keys.yml` запускается каждые 30 минут по `schedule` и вручную через `workflow_dispatch`.
- Из-за особенностей GitHub Actions scheduled workflow может запускаться с задержкой, а при высокой нагрузке отдельные окна могут быть пропущены.
- Чтобы уменьшить такие пропуски, cron смещён с начала часа на `17` и `47` минут каждого часа по UTC.
- Перед запуском checker workflow ставит официальный `sing-box` бинарник на `ubuntu-latest`.
- Параллелизм `sing-box`-проверок регулируется через `SINGBOX_WORKERS` и в workflow сейчас выставлен в `12`.

## Ограничения

- Проверка выполняется с GitHub-hosted runners, поэтому задержки и успешность `generate_204` отличаются от реальных у пользователя.
- `xhttp` и `security=none` сейчас исключаются до проверки как неподдерживаемые текущим пайплайном.
- Реальный `sing-box`-чек заметно строже простого `TCP`, поэтому число рабочих ключей может резко снизиться по сравнению с прошлой схемой.
- Поэтому `top15` строится не по минимальной задержке runner'а, а по стабильности прохождения серии чеков.

## Локальный запуск

```bash
git clone https://github.com/lilyungcykamane/vless-checker.git
cd vless-checker
python3 -m venv .venv
source .venv/bin/activate
pip install requests
curl -fsSL -o /tmp/sing-box.tar.gz "https://github.com/SagerNet/sing-box/releases/download/v1.13.5/sing-box-1.13.5-darwin-arm64.tar.gz"
tar -xzf /tmp/sing-box.tar.gz -C /tmp
export SING_BOX_BIN="/tmp/sing-box-1.13.5-darwin-arm64/sing-box"
python3 check_and_save.py
```

## GitHub Pages

После включения Pages сайт будет доступен по адресу:
[lilyungcykamane.github.io/vless-checker](https://lilyungcykamane.github.io/vless-checker/)

Основные подписки:

- [good.txt через jsDelivr](https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/good.txt)
- [top15.txt через jsDelivr](https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top15.txt)
- [good.txt через raw.githubusercontent.com](https://raw.githubusercontent.com/lilyungcykamane/vless-checker/refs/heads/main/good.txt)
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
├── singbox_utils.py     # E2E-проверка через sing-box
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
