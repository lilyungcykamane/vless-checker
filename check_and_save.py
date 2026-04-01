#!/usr/bin/env python3
import json
import os
from collections import Counter

from stability_utils import (
    history_now,
    history_summary,
    load_history,
    rank_working_results,
    save_history,
    select_stable_top15,
    update_history,
)
from vless_utils import (
    announce_line,
    count_transports,
    fetch_all_keys,
    filter_supported_keys,
    format_subscription_file,
    get_country_metadata,
    msk_timestamp,
    run_tcp_checks,
    utc_timestamp,
)

GOOD_KEYS_PATH = "good.txt"
TOP100_KEYS_PATH = "top100.txt"
TOP50_COMPAT_PATH = "top50.txt"
TOP15_COMPAT_PATH = "top15.txt"
KEYS_JSON_PATH = "docs/keys.json"
HISTORY_PATH = "history.json"
TOP_LIMIT = 100

FULL_PROFILE_TITLE = "Kerosin Обход БС (Full)"
TOP100_PROFILE_TITLE = "Kerosin Обход БС (TOP100)"

FULL_DOWNLOAD_URL = "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/good.txt"
TOP100_DOWNLOAD_URL = "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top100.txt"
TOP50_COMPAT_DOWNLOAD_URL = "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top50.txt"
TOP15_COMPAT_DOWNLOAD_URL = "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top15.txt"


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
            "median_latency_ms": item["median_latency_ms"],
            "availability_pct": item["availability_pct"],
            "success_streak": item["success_streak"],
            "observations": item["observations"],
            "stable_qualified": item["stable_qualified"],
            "country": get_country_metadata(item["key"])["country"],
            "flag": get_country_metadata(item["key"])["flag"],
        }
        for index, item in enumerate(entries, 1)
    ]


def main():
    print("Загружаем списки...")
    all_keys, source_stats = fetch_all_keys()
    candidate_keys, unsupported_reasons = filter_supported_keys(all_keys)
    transport_counts = count_transports(candidate_keys)
    for source_name, info in source_stats.items():
        if source_name == "combined":
            continue
        print(f"  {source_name}: {info['total']} ключей")
    print(f"Всего уникальных ключей после дедупликации: {source_stats['combined']['total']}")
    print(f"Кандидатов после prefilter: {len(candidate_keys)}")
    if unsupported_reasons:
        print(f"Пропущено по prefilter: {unsupported_reasons}")
    print(f"Транспортов: {transport_counts}")

    print("Проверяем ключи по TCP...")
    tcp_results = run_tcp_checks(candidate_keys, on_result=log_result)
    history = load_history(HISTORY_PATH)
    history = update_history(history, candidate_keys, tcp_results, run_timestamp=history_now())
    ranked_working_results = rank_working_results(tcp_results["working"], history)
    top100_results = select_stable_top15(ranked_working_results, limit=TOP_LIMIT)
    history_info = history_summary(history, ranked_working_results)

    source_stats["combined"]["working"] = len(ranked_working_results)
    source_stats["combined"]["eligible"] = len(candidate_keys)
    failed_reasons = Counter(item["reason"] for item in tcp_results["failed"])

    os.makedirs("docs", exist_ok=True)
    save_history(HISTORY_PATH, history)

    good_content = format_subscription_file(
        FULL_PROFILE_TITLE,
        [item["key"] for item in ranked_working_results],
    )
    top100_content = format_subscription_file(
        TOP100_PROFILE_TITLE,
        [item["key"] for item in top100_results],
    )

    write_text(
        GOOD_KEYS_PATH,
        good_content,
    )
    write_text(
        TOP100_KEYS_PATH,
        top100_content,
    )
    write_text(
        TOP50_COMPAT_PATH,
        top100_content,
    )
    write_text(
        TOP15_COMPAT_PATH,
        top100_content,
    )

    payload = {
        "updated_at": utc_timestamp(),
        "updated_at_msk": msk_timestamp(),
        "announce": announce_line(),
        "check_mode": "tcp",
        "downloads": {
            "full": FULL_DOWNLOAD_URL,
            "top100": TOP100_DOWNLOAD_URL,
            "top50": TOP50_COMPAT_DOWNLOAD_URL,
            "top15": TOP15_COMPAT_DOWNLOAD_URL,
        },
        "ranking": {
            "mode": "stability",
            **history_info,
        },
        "source_counts": source_stats,
        "transport_counts": transport_counts,
        "totals": {
            "unique": len(all_keys),
            "eligible": len(candidate_keys),
            "working": len(ranked_working_results),
            "top100": len(top100_results),
            "top50": len(top100_results),
            "top15": len(top100_results),
            "unsupported": sum(unsupported_reasons.values()),
            "failed": len(tcp_results["failed"]),
            "stable_candidates": history_info["stable_candidates"],
        },
        "unsupported_reasons": unsupported_reasons,
        "failed_reasons": dict(failed_reasons.most_common(10)),
        "top100": build_top_entries(top100_results),
        "top50": build_top_entries(top100_results),
        "top15": build_top_entries(top100_results),
    }

    with open(KEYS_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"Рабочих ключей: {len(ranked_working_results)}")
    print(f"Стабильных кандидатов: {history_info['stable_candidates']}")
    print(f"Топ-100 сохранён в {TOP100_KEYS_PATH}")
    print(f"Полная подписка сохранена в {GOOD_KEYS_PATH}")
    print(f"JSON для сайта сохранён в {KEYS_JSON_PATH}")
    print(f"История чеков сохранена в {HISTORY_PATH}")


if __name__ == "__main__":
    main()
