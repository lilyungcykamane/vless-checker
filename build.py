#!/usr/bin/env python3
"""Пайплайн: скачать источники → отфильтровать → реально проверить → отдать подписки."""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import policy
import probe
import sources
import stability
import vless_uri

GOOD_PATH = "good.txt"
TOP_PATH = "top100.txt"
COMPAT_PATHS = ("top50.txt", "top15.txt")
KEYS_JSON_PATH = "docs/keys.json"
HISTORY_PATH = "history.json"
TOP_LIMIT = int(os.environ.get("TOP_LIMIT", "100"))

FULL_PROFILE_TITLE = "Kerosin Обход БС (Full)"
TOP_PROFILE_TITLE = "Kerosin Обход БС (TOP100)"
SUPPORT_URL = "https://t.me/KerosinSupport"
CDN_BASE = "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker"
MSK = timezone(timedelta(hours=3), name="MSK")


def msk_timestamp():
    return datetime.now(MSK).strftime("%Y-%m-%d %H:%M МСК")


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def announce_line():
    return f"Последняя проверка: {msk_timestamp()}"


def format_subscription(title, entries):
    lines = [
        f"#profile-title: {title}",
        "#profile-update-interval: 1",
        f"#support-url: {SUPPORT_URL}",
        f"#announce: {announce_line()}",
        "",
    ]
    lines.extend(vless_uri.to_uri(entry, entry["name"]) for entry in entries)
    return "\n".join(lines).rstrip() + "\n"


def write_text(path, content):
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def json_entry(index, entry):
    return {
        "rank": index,
        "key": vless_uri.to_uri(entry, entry["name"]),
        "name": entry["name"],
        "host": entry["host"],
        "port": entry["port"],
        "country": entry["country"],
        "flag": entry["flag"],
        "transport": entry["transport"],
        "security": entry["security"],
        "source": entry["source"],
        "score": entry["score"],
        "latency_ms": entry["latency_ms"],
        "median_latency_ms": entry["median_latency_ms"],
        "availability_pct": entry["availability_pct"],
        "success_streak": entry["success_streak"],
        "observations": entry["observations"],
        "stable_qualified": entry["stable_qualified"],
    }


def log_batch(done, total, results, error):
    passed = sum(1 for result in results if result["ok"])
    suffix = f" | ошибка xray: {error}" if error else ""
    print(f"  проверено {done}/{total}, прошло в партии {passed}/{len(results)}{suffix}")


def main():
    print("Загружаем источники...")
    configs, source_stats = sources.fetch_all()
    for name, info in source_stats.items():
        if name == "combined":
            continue
        note = f" ОШИБКА: {info['error']}" if info.get("error") else ""
        print(f"  {name} (вес {info['weight']}): {info['total']}{note}")
    print(f"Уникальных после дедупликации: {source_stats['combined']['unique']}")

    if not configs:
        sys.exit("Ни один источник не отдал конфиги — выдачу не трогаем")

    candidates, rejected = policy.filter_configs(configs)
    print(f"Кандидатов после фильтра политики: {len(candidates)}")
    if rejected:
        print(f"Отброшено: {rejected}")
    if not candidates:
        sys.exit("После фильтра не осталось кандидатов — выдачу не трогаем")

    print(f"Проверяем {len(candidates)} конфигов через Xray...")
    results = probe.check_configs(candidates, on_batch=log_batch)
    checked = list(zip(candidates, results))
    working = [(config, result) for config, result in checked if result["ok"]]
    fail_reasons = Counter(
        result.get("reason", "fail") for _, result in checked if not result["ok"]
    )
    print(f"Прошли реальную проверку: {len(working)} из {len(candidates)}")
    if fail_reasons:
        print(f"Причины отказов: {dict(fail_reasons.most_common())}")

    if not working:
        sys.exit("Проверку не прошёл ни один конфиг — выдачу не трогаем")

    history = stability.update_history(
        stability.load_history(HISTORY_PATH), checked, run_timestamp=stability.history_now()
    )
    ranked = stability.rank_working(working, history)
    top = stability.select_top(ranked, TOP_LIMIT)

    policy.assign_names(ranked)
    stability_info = stability.summary(history, ranked)

    os.makedirs("docs", exist_ok=True)
    stability.save_history(HISTORY_PATH, history)

    good_content = format_subscription(FULL_PROFILE_TITLE, ranked)
    top_content = format_subscription(TOP_PROFILE_TITLE, top)
    write_text(GOOD_PATH, good_content)
    write_text(TOP_PATH, top_content)
    for path in COMPAT_PATHS:
        write_text(path, top_content)

    payload = {
        "updated_at": utc_timestamp(),
        "updated_at_msk": msk_timestamp(),
        "announce": announce_line(),
        "check_mode": "xray",
        "downloads": {
            "full": f"{CDN_BASE}/{GOOD_PATH}",
            "top100": f"{CDN_BASE}/{TOP_PATH}",
            "top50": f"{CDN_BASE}/top50.txt",
            "top15": f"{CDN_BASE}/top15.txt",
        },
        "ranking": {"mode": "stability+source_weight", **stability_info},
        "source_counts": source_stats,
        "transport_counts": dict(
            Counter(f"{entry['transport']}+{entry['security']}" for entry in ranked)
        ),
        "country_counts": dict(Counter(entry["country"] for entry in ranked).most_common()),
        "totals": {
            "unique": source_stats["combined"]["unique"],
            "eligible": len(candidates),
            "working": len(ranked),
            "top100": len(top),
            "top50": len(top),
            "top15": len(top),
            "unsupported": sum(rejected.values()),
            "failed": len(candidates) - len(working),
            "stable_candidates": stability_info["stable_candidates"],
        },
        "unsupported_reasons": rejected,
        "failed_reasons": dict(fail_reasons.most_common(10)),
        "top100": [json_entry(index, entry) for index, entry in enumerate(top, 1)],
    }
    payload["top50"] = payload["top100"]
    payload["top15"] = payload["top100"]

    with open(KEYS_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"Рабочих: {len(ranked)}, стабильных: {stability_info['stable_candidates']}")
    print(f"Записано: {GOOD_PATH}, {TOP_PATH}, {KEYS_JSON_PATH}, {HISTORY_PATH}")


if __name__ == "__main__":
    main()
