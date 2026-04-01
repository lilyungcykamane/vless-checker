#!/usr/bin/env python3
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape as html_unescape
from urllib.parse import parse_qs, quote, unquote, urlparse, urlsplit
import socket
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36"
    )
}

SOURCE_SPECS = [
    (
        "igareck_white_cidr_all",
        "https://github.com/igareck/vpn-configs-for-russia/blob/main/WHITE-CIDR-RU-all.txt",
    ),
    (
        "igareck_mobile_1",
        "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    ),
    (
        "igareck_mobile_2",
        "https://github.com/igareck/vpn-configs-for-russia/blob/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
    ),
    (
        "igareck_white_checked",
        "https://github.com/igareck/vpn-configs-for-russia/blob/main/WHITE-CIDR-RU-checked.txt",
    ),
    (
        "flexiy0_russia_whitelist",
        "https://raw.githubusercontent.com/FLEXIY0/matryoshka-vpn/refs/heads/main/configs/russia_whitelist.txt",
    ),
    (
        "avencores_githubmirror_26",
        "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/refs/heads/main/githubmirror/26.txt",
    ),
    (
        "whoahaow_bypass_all",
        "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/bypass/bypass-all.txt",
    ),
]

COUNTRY_WORD_RE = r"(?:[A-Z][A-Za-z\u00C0-\u017E']*|and|of|the)"
COUNTRY_FRAGMENT_RE = re.compile(
    rf"(?P<country>{COUNTRY_WORD_RE}(?:[ -]{COUNTRY_WORD_RE})*)(?=\s*(?:,|\||\[|$))"
)

MSK = timezone(timedelta(hours=3), name="MSK")
MAX_TCP_WORKERS = 20
TEST_TIMEOUT = 5
MAX_LATENCY_MS = 2000
UNSUPPORTED_TRANSPORTS = {"xhttp"}
UNSUPPORTED_SECURITIES = {"none", ""}
REGIONAL_INDICATOR_START = 0x1F1E6
REGIONAL_INDICATOR_END = 0x1F1FF
FLAG_COUNTRY_NAMES = {
    "AE": "United Arab Emirates",
    "AL": "Albania",
    "AT": "Austria",
    "BG": "Bulgaria",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CN": "China",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FM": "Micronesia",
    "FR": "France",
    "GB": "United Kingdom",
    "ID": "Indonesia",
    "IN": "India",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "KZ": "Kazakhstan",
    "LT": "Lithuania",
    "LV": "Latvia",
    "MD": "Moldova",
    "ME": "Montenegro",
    "NL": "The Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "RS": "Serbia",
    "RU": "Russia",
    "SE": "Sweden",
    "SG": "Singapore",
    "TM": "Turkmenistan",
    "TR": "Turkey",
    "UA": "Ukraine",
    "UN": "United Nations",
    "US": "United States",
}


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


def build_source_urls():
    source_urls = {}
    seen_urls = set()

    for name, url in SOURCE_SPECS:
        normalized_url = normalize_source_url(url)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        source_urls[name] = url

    return source_urls


SOURCE_URLS = build_source_urls()


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


def find_first_flag_emoji(text):
    if not text:
        return None

    for index in range(len(text) - 1):
        first = ord(text[index])
        second = ord(text[index + 1])
        if (
            REGIONAL_INDICATOR_START <= first <= REGIONAL_INDICATOR_END
            and REGIONAL_INDICATOR_START <= second <= REGIONAL_INDICATOR_END
        ):
            return text[index:index + 2]

    return None


def flag_emoji_to_country_code(flag_emoji):
    if not flag_emoji or len(flag_emoji) != 2:
        return None

    chars = []
    for char in flag_emoji:
        codepoint = ord(char)
        if not (REGIONAL_INDICATOR_START <= codepoint <= REGIONAL_INDICATOR_END):
            return None
        chars.append(chr(ord("A") + codepoint - REGIONAL_INDICATOR_START))

    return "".join(chars)


def flag_emoji_to_country_name(flag_emoji):
    country_code = flag_emoji_to_country_code(flag_emoji)
    if not country_code:
        return None

    return FLAG_COUNTRY_NAMES.get(country_code)


def normalize_key(key):
    key = html_unescape(key.strip())
    if not key.startswith("vless://"):
        return None

    base = key.split("#", 1)[0]
    fragment = unquote(key.split("#", 1)[1]).strip() if "#" in key else ""
    flag_emoji = find_first_flag_emoji(fragment)
    country_name = flag_emoji_to_country_name(flag_emoji) if flag_emoji else None

    if country_name:
        display_name = f"{flag_emoji} {country_name}"
    else:
        display_name = "Cosmos"

    return f"{base}#{quote(display_name, safe='')}"


def fetch_keys(url):
    raw_url = normalize_source_url(url)
    response = requests.get(raw_url, timeout=15, headers=REQUEST_HEADERS)
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
        try:
            keys = fetch_keys(url)
            source_stats[name] = {
                "url": url,
                "raw_url": normalize_source_url(url),
                "total": len(keys),
            }
            all_keys.extend(keys)
        except requests.RequestException as error:
            source_stats[name] = {
                "url": url,
                "raw_url": normalize_source_url(url),
                "total": 0,
                "error": str(error),
            }

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
            query.get("allowinsecure")
            or query.get("allowInsecure")
            or query.get("insecure")
            or ""
        ).lower() in {"1", "true", "yes"},
    }


def get_country_metadata(key):
    country, flag = parse_country_from_key(key)
    if country:
        return {
            "country": country,
            "flag": flag or "",
        }

    return {
        "country": "Cosmos",
        "flag": "",
    }


def count_transports(keys):
    counter = Counter()
    for key in keys:
        counter[normalize_transport(parse_vless_key(key)["transport"])] += 1
    return dict(counter)


def parse_host_port(key):
    try:
        parsed = parse_vless_key(key)
    except ValueError:
        return None, None
    return parsed["server"], parsed["server_port"]


def normalize_transport(transport):
    normalized = (transport or "tcp").strip().lower()
    if normalized == "raw":
        return "tcp"
    return normalized


def filter_supported_keys(keys):
    filtered = []
    unsupported_reasons = Counter()

    for key in keys:
        try:
            parsed = parse_vless_key(key)
        except ValueError:
            unsupported_reasons["invalid_uri"] += 1
            continue

        if parsed["allow_insecure"]:
            unsupported_reasons["insecure"] += 1
            continue

        security = (parsed["security"] or "").strip().lower()
        if security in UNSUPPORTED_SECURITIES:
            unsupported_reasons["security_none"] += 1
            continue

        transport = normalize_transport(parsed["transport"])
        if transport in UNSUPPORTED_TRANSPORTS:
            unsupported_reasons[transport] += 1
            continue

        filtered.append(key)

    return dedupe_keys(filtered), dict(unsupported_reasons)


def build_endpoint_groups(keys):
    groups = {}
    invalid_results = []

    for key in keys:
        host, port = parse_host_port(key)
        if not host or not port:
            invalid_results.append(
                {
                    "status": "invalid",
                    "key": key,
                    "host": host,
                    "port": port,
                    "reason": "invalid",
                }
            )
            continue

        endpoint = (host.lower(), int(port))
        groups.setdefault(endpoint, []).append(key)

    return groups, invalid_results


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
    endpoint_groups, invalid_results = build_endpoint_groups(keys)
    results = list(invalid_results)

    with ThreadPoolExecutor(max_workers=MAX_TCP_WORKERS) as executor:
        futures = {
            executor.submit(test_key_tcp, group_keys[0]): endpoint
            for endpoint, group_keys in endpoint_groups.items()
        }
        total = len(futures)
        done = 0

        for future in as_completed(futures):
            result = future.result()
            done += 1
            if on_result:
                on_result(done, total, result)
            endpoint = futures[future]
            for key in endpoint_groups[endpoint]:
                replicated = dict(result)
                replicated["key"] = key
                results.append(replicated)

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
