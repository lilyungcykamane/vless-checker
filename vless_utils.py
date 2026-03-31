#!/usr/bin/env python3
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote, unquote, urlparse, urlsplit
import socket
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

CIDRALL = "https://github.com/igareck/vpn-configs-for-russia/blob/main/WHITE-CIDR-RU-all.txt"
CIDRTOP1501 = "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile.txt"
CIDRTOP1502 = "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt"
CIDRCHECKED = "https://github.com/igareck/vpn-configs-for-russia/blob/main/WHITE-CIDR-RU-checked.txt"

SOURCE_URLS = {
    "cidr_all": CIDRALL,
    "cidr_top150_1": CIDRTOP1501,
    "cidr_top150_2": CIDRTOP1502,
    "cidr_checked": CIDRCHECKED,
}

COUNTRY_WORD_RE = r"(?:[A-Z][A-Za-z\u00C0-\u017E']*|and|of|the)"
COUNTRY_FRAGMENT_RE = re.compile(
    rf"(?P<country>{COUNTRY_WORD_RE}(?:[ -]{COUNTRY_WORD_RE})*)(?=\s*(?:,|\||\[|$))"
)

MSK = timezone(timedelta(hours=3), name="MSK")
MAX_TCP_WORKERS = 20
TEST_TIMEOUT = 5
MAX_LATENCY_MS = 2000


def normalize_source_url(url):
    parsed = urlparse(url)
    if parsed.netloc != "github.com":
        return url

    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 5 and parts[2] == "blob":
        owner, repo, _, branch = parts[:4]
        rest = "/".join(parts[4:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rest}"

    return url


def dedupe_keys(keys):
    return list(dict.fromkeys(keys))


def parse_country_from_key(key):
    if "#" not in key:
        return None, None

    fragment = unquote(key.split("#", 1)[1]).strip()
    match = COUNTRY_FRAGMENT_RE.search(fragment)
    if not match:
        return None, None

    country = match.group("country").strip()
    flag = fragment[: match.start("country")].strip()
    return country, flag


def normalize_key(key):
    key = key.strip()
    if not key.startswith("vless://"):
        return None

    if "#" not in key:
        return key

    base, fragment = key.split("#", 1)
    country, flag = parse_country_from_key(key)
    if not country:
        return f"{base}#{fragment}"

    cleaned_fragment = " ".join(part for part in (flag, country) if part).strip()
    return f"{base}#{quote(cleaned_fragment, safe='')}"


def fetch_keys(url):
    raw_url = normalize_source_url(url)
    response = requests.get(raw_url, timeout=15)
    response.raise_for_status()

    keys = []
    for line in response.text.splitlines():
        normalized = normalize_key(line)
        if normalized:
            keys.append(normalized)
    return dedupe_keys(keys)


def fetch_all_keys():
    source_stats = {}
    all_keys = []

    for name, url in SOURCE_URLS.items():
        keys = fetch_keys(url)
        source_stats[name] = {
            "url": url,
            "raw_url": normalize_source_url(url),
            "total": len(keys),
        }
        all_keys.extend(keys)

    deduped_keys = dedupe_keys(all_keys)
    source_stats["combined"] = {"total": len(deduped_keys)}
    return deduped_keys, source_stats


def parse_vless_key(key):
    parsed = urlsplit(key)
    query = {
        name: values[-1]
        for name, values in parse_qs(parsed.query, keep_blank_values=True).items()
    }

    return {
        "key": key,
        "uuid": parsed.username,
        "server": parsed.hostname,
        "server_port": parsed.port,
        "transport": query.get("type", "tcp").lower(),
        "security": query.get("security", "none").lower(),
        "sni": query.get("sni") or query.get("serverName") or "",
        "public_key": query.get("pbk", ""),
        "short_id": query.get("sid", ""),
        "fingerprint": (query.get("fp") or "chrome").lower(),
        "flow": query.get("flow", ""),
        "service_name": query.get("serviceName") or query.get("service_name") or "",
        "packet_encoding": query.get("packetEncoding") or query.get("packet_encoding") or "",
        "mode": query.get("mode", ""),
        "extra": query.get("extra", ""),
        "allow_insecure": (
            query.get("allowinsecure") or query.get("allowInsecure") or ""
        ).lower() in {"1", "true", "yes"},
    }


def get_country_metadata(key):
    country, flag = parse_country_from_key(key)
    if country:
        return {
            "country": country,
            "flag": flag or "🌍",
        }

    return {
        "country": "Unknown",
        "flag": "🌍",
    }


def count_transports(keys):
    counter = Counter()
    for key in keys:
        counter[parse_vless_key(key)["transport"]] += 1
    return dict(counter)


def parse_host_port(key):
    parsed = parse_vless_key(key)
    return parsed["server"], parsed["server_port"]


def test_key_tcp(key):
    host, port = parse_host_port(key)
    if not host or not port:
        return {
            "status": "invalid",
            "key": key,
            "host": host,
            "port": port,
            "reason": "invalid",
        }

    try:
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except Exception:
        return {
            "status": "error",
            "key": key,
            "host": host,
            "port": port,
            "reason": "dns",
        }

    best = None
    for family, socktype, proto, _, sockaddr in infos:
        start = time.time()
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(TEST_TIMEOUT)
            result = sock.connect_ex(sockaddr)
            sock.close()
            elapsed = round((time.time() - start) * 1000, 1)
            if result == 0 and elapsed <= MAX_LATENCY_MS:
                if best is None or elapsed < best["latency_ms"]:
                    best = {
                        "status": "ok",
                        "key": key,
                        "host": host,
                        "port": port,
                        "latency_ms": elapsed,
                    }
        except Exception:
            continue

    if best:
        return best

    return {
        "status": "error",
        "key": key,
        "host": host,
        "port": port,
        "reason": "tcp",
    }


def run_tcp_checks(keys, on_result=None):
    results = []
    with ThreadPoolExecutor(max_workers=MAX_TCP_WORKERS) as executor:
        futures = {executor.submit(test_key_tcp, key): key for key in keys}
        total = len(futures)
        done = 0

        for future in as_completed(futures):
            result = future.result()
            done += 1
            if on_result:
                on_result(done, total, result)
            results.append(result)

    working = sorted(
        [item for item in results if item["status"] == "ok"],
        key=lambda item: item["latency_ms"],
    )
    failed = [item for item in results if item["status"] != "ok"]

    return {
        "working": working,
        "failed": failed,
    }


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def msk_timestamp():
    return datetime.now(MSK).strftime("%Y-%m-%d %H:%M МСК")


def announce_line():
    return f"Последнее сканирование: {msk_timestamp()}"


def format_subscription_file(profile_title, keys):
    lines = [
        f"#profile-title: {profile_title}",
        "#profile-update-interval: 1",
        "#support-url: https://t.me/KerosinSupport",
        f"#announce: {announce_line()}",
        "",
    ]
    lines.extend(keys)
    return "\n".join(lines).rstrip() + "\n"
