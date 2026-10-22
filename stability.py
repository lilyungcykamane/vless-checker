#!/usr/bin/env python3
"""История проверок и рейтинг по стабильности."""
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median

import vless_uri

UTC = timezone.utc

HISTORY_SCHEMA_VERSION = 2
HISTORY_WINDOW = 96
MIN_OBSERVATIONS_FOR_STABLE = 6
MIN_AVAILABILITY_PCT = 80.0
MIN_SUCCESS_STREAK = 2
STALE_RETENTION_DAYS = 7

# Вес стабильности против веса источника: стабильность важнее, но при близких
# показателях вперёд выходит конфиг приоритетного источника.
STABLE_BONUS = 60.0
STREAK_POINTS = 2.0
STREAK_CAP = 12
HOST_CAP = int(os.environ.get("TOP_HOST_CAP", "4"))


def history_now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def history_key(config):
    """Ключ истории не зависит от имени конфига — переименование не обнуляет статистику."""
    raw = "|".join(str(part) for part in vless_uri.identity(config))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def empty_history():
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "window_size": HISTORY_WINDOW,
        "updated_at": None,
        "items": {},
    }


def load_history(path):
    if not os.path.exists(path):
        return empty_history()

    try:
        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError):
        return empty_history()

    if not isinstance(raw, dict) or raw.get("schema_version") != HISTORY_SCHEMA_VERSION:
        return empty_history()

    items = {}
    for key, record in (raw.get("items") or {}).items():
        if not isinstance(record, dict):
            continue
        samples = [
            sample
            for sample in record.get("history", [])
            if isinstance(sample, dict) and "ts" in sample
        ]
        items[key] = {
            "endpoint": record.get("endpoint"),
            "first_seen_at": record.get("first_seen_at"),
            "last_seen_at": record.get("last_seen_at"),
            "last_success_at": record.get("last_success_at"),
            "last_failure_at": record.get("last_failure_at"),
            "last_status": record.get("last_status"),
            "history": samples[-HISTORY_WINDOW:],
        }

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "window_size": HISTORY_WINDOW,
        "updated_at": raw.get("updated_at"),
        "items": items,
    }


def save_history(path, history):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)


def update_history(history, checked, run_timestamp=None):
    """checked — список (config, result) после реальной проверки."""
    run_timestamp = run_timestamp or history_now()
    items = dict(history.get("items", {}))
    current = set()

    for config, result in checked:
        key = history_key(config)
        current.add(key)
        record = items.get(key, {})
        samples = list(record.get("history", []))
        ok = bool(result.get("ok"))

        sample = {"ts": run_timestamp, "ok": ok}
        if ok:
            sample["latency_ms"] = round(float(result["latency_ms"]), 1)
        else:
            sample["reason"] = result.get("reason", "fail")
        samples.append(sample)

        items[key] = {
            "endpoint": vless_uri.endpoint(config),
            "first_seen_at": record.get("first_seen_at") or run_timestamp,
            "last_seen_at": run_timestamp,
            "last_success_at": run_timestamp if ok else record.get("last_success_at"),
            "last_failure_at": run_timestamp if not ok else record.get("last_failure_at"),
            "last_status": "ok" if ok else sample["reason"],
            "history": samples[-HISTORY_WINDOW:],
        }

    cutoff = parse_timestamp(run_timestamp)
    if cutoff:
        cutoff -= timedelta(days=STALE_RETENTION_DAYS)
        items = {
            key: record
            for key, record in items.items()
            if key in current or (parse_timestamp(record.get("last_seen_at")) or cutoff) >= cutoff
        }

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "window_size": HISTORY_WINDOW,
        "updated_at": run_timestamp,
        "items": items,
    }


def metrics_for(record):
    samples = record.get("history", [])
    observations = len(samples)
    successful = [sample for sample in samples if sample.get("ok")]
    availability_pct = (
        round(len(successful) / observations * 100, 1) if observations else 0.0
    )

    success_streak = 0
    for sample in reversed(samples):
        if not sample.get("ok"):
            break
        success_streak += 1

    latencies = [
        float(sample["latency_ms"])
        for sample in successful
        if isinstance(sample.get("latency_ms"), (int, float))
    ]
    median_latency_ms = round(median(latencies), 1) if latencies else None

    return {
        "observations": observations,
        "successful_observations": len(successful),
        "availability_pct": availability_pct,
        "success_streak": success_streak,
        "median_latency_ms": median_latency_ms,
        "stable_qualified": (
            observations >= MIN_OBSERVATIONS_FOR_STABLE
            and availability_pct >= MIN_AVAILABILITY_PCT
            and success_streak >= MIN_SUCCESS_STREAK
        ),
        "first_seen_at": record.get("first_seen_at"),
        "last_success_at": record.get("last_success_at"),
    }


def score_of(entry):
    return (
        entry["availability_pct"]
        + min(entry["success_streak"], STREAK_CAP) * STREAK_POINTS
        + entry["source_weight"]
        + (STABLE_BONUS if entry["stable_qualified"] else 0.0)
    )


def rank_working(working, history):
    """working — список (config, result) только по прошедшим проверку."""
    items = history.get("items", {})
    entries = []

    for config, result in working:
        record = items.get(history_key(config), {"history": []})
        entry = dict(config)
        entry["latency_ms"] = result["latency_ms"]
        entry.update(metrics_for(record))
        entry["score"] = round(score_of(entry), 1)
        entries.append(entry)

    entries.sort(
        key=lambda entry: (
            -entry["score"],
            entry["median_latency_ms"] if entry["median_latency_ms"] is not None else float("inf"),
            entry["latency_ms"],
            entry["host"],
            entry["port"],
        )
    )
    return entries


def select_top(ranked, limit, host_cap=HOST_CAP):
    """Топ с ограничением на число конфигов с одного хоста — чтобы подписка не легла вместе с одним сервером."""
    order = {id(entry): index for index, entry in enumerate(ranked)}
    selected = []
    per_host = Counter()

    for entry in ranked:
        if len(selected) >= limit:
            break
        if per_host[entry["host"]] >= host_cap:
            continue
        per_host[entry["host"]] += 1
        selected.append(entry)

    if len(selected) < limit:
        chosen = {id(entry) for entry in selected}
        for entry in ranked:
            if len(selected) >= limit:
                break
            if id(entry) not in chosen:
                selected.append(entry)

    # Порядок в файле должен совпадать с рейтингом, даже если лимит по хосту
    # сдвинул часть конфигов на второй проход.
    selected.sort(key=lambda entry: order[id(entry)])
    return selected


def summary(history, ranked):
    return {
        "tracked_keys": len(history.get("items", {})),
        "history_window": HISTORY_WINDOW,
        "min_observations": MIN_OBSERVATIONS_FOR_STABLE,
        "min_availability_pct": MIN_AVAILABILITY_PCT,
        "min_success_streak": MIN_SUCCESS_STREAK,
        "top_host_cap": HOST_CAP,
        "stable_candidates": sum(1 for entry in ranked if entry["stable_qualified"]),
    }
