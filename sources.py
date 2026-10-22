#!/usr/bin/env python3
"""Источники конфигов и их веса.

weight влияет на итоговый рейтинг: чем выше, чем раньше конфиги источника
попадают в top-подписку при равной стабильности.
"""
import urllib.error
import urllib.request

import vless_uri

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 20

SOURCES = [
    # zieng2/wl — приоритетный источник. vless.txt не берём: там лежат
    # три конфига-заглушки с предупреждением об устаревшей подписке.
    {
        "name": "zieng2_universal",
        "url": "https://raw.githubusercontent.com/zieng2/wl/main/vless_universal.txt",
        "weight": 30,
    },
    {
        "name": "zieng2_lite",
        "url": "https://raw.githubusercontent.com/zieng2/wl/main/vless_lite.txt",
        "weight": 30,
    },
    # igareck/vpn-configs-for-russia — берём только белые списки.
    # BLACK_* из того же репозитория здесь не нужны: это конфиги для обычного
    # обхода блокировок, а не для режима белых списков.
    {
        "name": "igareck_white_cidr_all",
        "url": "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-all.txt",
        "weight": 10,
    },
    {
        "name": "igareck_white_cidr_checked",
        "url": "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-checked.txt",
        "weight": 10,
    },
    {
        "name": "igareck_white_sni_all",
        "url": "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-SNI-RU-all.txt",
        "weight": 10,
    },
    {
        "name": "igareck_white_reality_mobile",
        "url": "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
        "weight": 10,
    },
]


def fetch_source(source):
    request = urllib.request.Request(source["url"], headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        body = response.read().decode("utf-8", "replace")

    configs = []
    for line in body.splitlines():
        config = vless_uri.parse(line)
        if config:
            config["source"] = source["name"]
            config["source_weight"] = source["weight"]
            configs.append(config)
    return configs


def fetch_all():
    """Скачать все источники и слить их с дедупликацией.

    При одинаковой точке входа выживает конфиг источника с большим весом.
    """
    stats = {}
    collected = []

    for source in SOURCES:
        try:
            configs = fetch_source(source)
            stats[source["name"]] = {
                "url": source["url"],
                "weight": source["weight"],
                "total": len(configs),
            }
            collected.extend(configs)
        except (urllib.error.URLError, OSError, ValueError) as error:
            stats[source["name"]] = {
                "url": source["url"],
                "weight": source["weight"],
                "total": 0,
                "error": str(error),
            }

    # Сначала источники с высоким весом — при дедупликации они и остаются.
    collected.sort(key=lambda config: -config["source_weight"])

    deduped = {}
    for config in collected:
        identity = vless_uri.identity(config)
        if identity not in deduped:
            deduped[identity] = config

    unique = list(deduped.values())
    stats["combined"] = {"fetched": len(collected), "unique": len(unique)}
    return unique, stats
