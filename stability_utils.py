#!/usr/bin/env python3
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median

UTC = timezone.utc

HISTORY_SCHEMA_VERSION = 1
HISTORY_WINDOW = 96
MIN_OBSERVATIONS_FOR_STABLE = 8
MIN_AVAILABILITY_PCT = 85.0
MIN_SUCCESS_STREAK = 3
TOP_HOST_CAP = 1
STALE_RETENTION_DAYS = 14


def history_now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_history_timestamp(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def empty_history():
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "window_size": HISTORY_WINDOW,
        "updated_at": None,
        "items": {},
    }


def normalize_sample(sample):
    if not isinstance(sample, dict):
        return None

    ts = sample.get("ts")
    ok = bool(sample.get("ok"))
    normalized = {"ts": ts, "ok": ok}

    latency_ms = sample.get("latency_ms")
    if ok and isinstance(latency_ms, (int, float)):
        normalized["latency_ms"] = round(float(latency_ms), 1)

    reason = sample.get("reason")
    if not ok and isinstance(reason, str) and reason:
        normalized["reason"] = reason

    return normalized


def normalize_history_record(record):
    if not isinstance(record, dict):
        return None

    samples = []
    for sample in record.get("history", []):
        normalized_sample = normalize_sample(sample)
        if normalized_sample:
            samples.append(normalized_sample)

    if not samples and not record.get("first_seen_at"):
        return None

    return {
        "first_seen_at": record.get("first_seen_at"),
        "last_seen_at": record.get("last_seen_at"),
        "last_success_at": record.get("last_success_at"),
        "last_failure_at": record.get("last_failure_at"),
        "last_status": record.get("last_status"),
        "history": samples[-HISTORY_WINDOW:],
    }


def load_history(path):
    if not os.path.exists(path):
        return empty_history()

    try:
        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except Exception:
        return empty_history()

    if not isinstance(raw, dict):
        return empty_history()

    items = {}
    for key, record in raw.get("items", {}).items():
        if not isinstance(key, str):
            continue
        normalized = normalize_history_record(record)
        if normalized:
            items[key] = normalized

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "window_size": HISTORY_WINDOW,
        "updated_at": raw.get("updated_at"),
        "items": items,
    }


def save_history(path, history_state):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(history_state, file, ensure_ascii=False, indent=2)


def update_history(history_state, current_keys, tcp_results, run_timestamp=None):
    run_timestamp = run_timestamp or history_now()
    items = dict(history_state.get("items", {}))
    result_map = {
        item["key"]: item
        for item in tcp_results["working"] + tcp_results["failed"]
    }

    for key in current_keys:
        result = result_map.get(key, {"status": "error", "reason": "missing"})
        record = items.get(key, {})
        samples = list(record.get("history", []))
        ok = result["status"] == "ok"

        sample = {"ts": run_timestamp, "ok": ok}
        if ok:
            sample["latency_ms"] = round(float(result["latency_ms"]), 1)
        else:
            sample["reason"] = result.get("reason", result["status"])

        samples.append(sample)
        samples = samples[-HISTORY_WINDOW:]

        items[key] = {
            "first_seen_at": record.get("first_seen_at") or run_timestamp,
            "last_seen_at": run_timestamp,
            "last_success_at": run_timestamp if ok else record.get("last_success_at"),
            "last_failure_at": run_timestamp if not ok else record.get("last_failure_at"),
            "last_status": "ok" if ok else sample["reason"],
            "history": samples,
        }

    cutoff = parse_history_timestamp(run_timestamp)
    if cutoff:
        cutoff -= timedelta(days=STALE_RETENTION_DAYS)
        current_key_set = set(current_keys)
        kept_items = {}
        for key, record in items.items():
            if key in current_key_set:
                kept_items[key] = record
                continue

            last_seen = parse_history_timestamp(record.get("last_seen_at"))
            if last_seen and last_seen >= cutoff:
                kept_items[key] = record
        items = kept_items

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "window_size": HISTORY_WINDOW,
        "updated_at": run_timestamp,
        "items": items,
    }


def build_stability_metrics(history_record):
    samples = history_record.get("history", [])
    observations = len(samples)
    successful_samples = [sample for sample in samples if sample.get("ok")]
    successful_observations = len(successful_samples)
    availability_pct = round((successful_observations / observations) * 100, 1) if observations else 0.0

    success_streak = 0
    for sample in reversed(samples):
        if sample.get("ok"):
            success_streak += 1
            continue
        break

    latency_values = [
        round(float(sample["latency_ms"]), 1)
        for sample in successful_samples
        if isinstance(sample.get("latency_ms"), (int, float))
    ]
    median_latency_ms = round(float(median(latency_values)), 1) if latency_values else None
    stable_qualified = (
        observations >= MIN_OBSERVATIONS_FOR_STABLE
        and availability_pct >= MIN_AVAILABILITY_PCT
        and success_streak >= MIN_SUCCESS_STREAK
    )

    return {
        "observations": observations,
        "successful_observations": successful_observations,
        "availability_pct": availability_pct,
        "success_streak": success_streak,
        "median_latency_ms": median_latency_ms,
        "stable_qualified": stable_qualified,
        "first_seen_at": history_record.get("first_seen_at"),
        "last_success_at": history_record.get("last_success_at"),
        "last_failure_at": history_record.get("last_failure_at"),
    }


def merge_working_results_with_history(working_results, history_state):
    items = history_state.get("items", {})
    merged = []

    for result in working_results:
        record = items.get(result["key"], {"history": []})
        metrics = build_stability_metrics(record)
        merged.append(
            {
                **result,
                **metrics,
            }
        )

    return merged


def stability_sort_key(item):
    median_latency_ms = item.get("median_latency_ms")
    current_latency_ms = item.get("latency_ms")

    return (
        not item.get("stable_qualified", False),
        -float(item.get("availability_pct", 0.0)),
        -int(item.get("success_streak", 0)),
        -int(item.get("successful_observations", 0)),
        median_latency_ms if isinstance(median_latency_ms, (int, float)) else float("inf"),
        current_latency_ms if isinstance(current_latency_ms, (int, float)) else float("inf"),
        item.get("first_seen_at") or "9999-12-31T23:59:59Z",
        item.get("host") or "",
        item.get("port") or 0,
        item.get("key") or "",
    )


def rank_working_results(working_results, history_state):
    merged = merge_working_results_with_history(working_results, history_state)
    return sorted(merged, key=stability_sort_key)


def select_stable_top15(ranked_results, limit=50):
    selected = []
    selected_keys = set()
    host_counts = Counter()

    def can_add(item):
        host = item.get("host") or item.get("server") or ""
        return host_counts[host] < TOP_HOST_CAP

    def add_item(item):
        host = item.get("host") or item.get("server") or ""
        selected.append(item)
        selected_keys.add(item["key"])
        host_counts[host] += 1

    for item in ranked_results:
        if not item.get("stable_qualified"):
            continue
        if can_add(item):
            add_item(item)
        if len(selected) >= limit:
            return selected

    for item in ranked_results:
        if item["key"] in selected_keys:
            continue
        if can_add(item):
            add_item(item)
        if len(selected) >= limit:
            return selected

    for item in ranked_results:
        if item["key"] in selected_keys:
            continue
        add_item(item)
        if len(selected) >= limit:
            return selected

    return selected


def history_summary(history_state, ranked_results):
    items = history_state.get("items", {})
    stable_candidates = sum(1 for item in ranked_results if item.get("stable_qualified"))

    return {
        "tracked_keys": len(items),
        "history_window": HISTORY_WINDOW,
        "min_observations": MIN_OBSERVATIONS_FOR_STABLE,
        "min_availability_pct": MIN_AVAILABILITY_PCT,
        "min_success_streak": MIN_SUCCESS_STREAK,
        "top_host_cap": TOP_HOST_CAP,
        "top15_host_cap": TOP_HOST_CAP,
        "stable_candidates": stable_candidates,
    }
