#!/usr/bin/env python3
import json
import os
from collections import Counter

from vless_utils import (
    announce_line,
    count_transports,
    fetch_all_keys,
    format_subscription_file,
    get_country_metadata,
    msk_timestamp,
    run_tcp_checks,
    utc_timestamp,
)

GOOD_KEYS_PATH = "good.txt"
TOP15_KEYS_PATH = "top15.txt"
KEYS_JSON_PATH = "docs/keys.json"

FULL_PROFILE_TITLE = "Kerosin Белые Списки (Full)"
TOP15_PROFILE_TITLE = "Kerosin Белые Списки (TOP15)"

FULL_DOWNLOAD_URL = "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker@main/good.txt"
TOP15_DOWNLOAD_URL = "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker@main/top15.txt"


def write_text(path, content):
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def log_result(done, total, result):
    status = result["status"]
    if status == "ok":
        print(
            f"[{done}/{total}] OK {result['host']}:{result['port']} "
            f"{result['latency_ms']} ms"
        )
        return

    if done % 25 != 0 and done != total:
        return

    print(
        f"[{done}/{total}] {status.upper()} {result.get('host') or '?'}:{result.get('port') or '?'} "
        f"{result['reason']}"
    )


def build_top_entries(entries):
    return [
        {
            "rank": index,
            "key": item["key"],
            "host": item["host"],
            "port": item["port"],
            "latency_ms": item["latency_ms"],
            "country": get_country_metadata(item["key"])["country"],
            "flag": get_country_metadata(item["key"])["flag"],
        }
        for index, item in enumerate(entries, 1)
    ]


def main():
    print("Загружаем списки...")
    all_keys, source_stats = fetch_all_keys()
    transport_counts = count_transports(all_keys)
    for source_name, info in source_stats.items():
        if source_name == "combined":
            continue
        print(f"  {source_name}: {info['total']} ключей")
    print(f"Всего уникальных ключей после дедупликации: {source_stats['combined']['total']}")
    print(f"Транспортов: {transport_counts}")

    print("Проверяем ключи по TCP...")
    tcp_results = run_tcp_checks(all_keys, on_result=log_result)
    working_results = tcp_results["working"]
    top15_results = working_results[:15]

    source_stats["combined"]["working"] = len(working_results)
    failed_reasons = Counter(item["reason"] for item in tcp_results["failed"])

    os.makedirs("docs", exist_ok=True)

    write_text(
        GOOD_KEYS_PATH,
        format_subscription_file(
            FULL_PROFILE_TITLE,
            [item["key"] for item in working_results],
        ),
    )
    write_text(
        TOP15_KEYS_PATH,
        format_subscription_file(
            TOP15_PROFILE_TITLE,
            [item["key"] for item in top15_results],
        ),
    )

    payload = {
        "updated_at": utc_timestamp(),
        "updated_at_msk": msk_timestamp(),
        "announce": announce_line(),
        "check_mode": "tcp",
        "downloads": {
            "full": FULL_DOWNLOAD_URL,
            "top15": TOP15_DOWNLOAD_URL,
        },
        "source_counts": source_stats,
        "transport_counts": transport_counts,
        "totals": {
            "unique": len(all_keys),
            "working": len(working_results),
            "top15": len(top15_results),
            "unsupported": 0,
            "failed": len(tcp_results["failed"]),
        },
        "unsupported_reasons": {},
        "failed_reasons": dict(failed_reasons.most_common(10)),
        "top15": build_top_entries(top15_results),
    }

    with open(KEYS_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"Рабочих ключей: {len(working_results)}")
    print(f"Топ-15 сохранён в {TOP15_KEYS_PATH}")
    print(f"Полная подписка сохранена в {GOOD_KEYS_PATH}")
    print(f"JSON для сайта сохранён в {KEYS_JSON_PATH}")


if __name__ == "__main__":
    main()
