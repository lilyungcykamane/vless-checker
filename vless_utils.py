#!/usr/bin/env python3
from collections import Counter
from datetime import datetime, timedelta, timezone
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
]

# Disabled candidate sources from the previous expansion. Keep nearby for quick rollback.
# (
#     "whoahaow_bypass_all",
#     "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/bypass/bypass-all.txt",
# ),
# (
#     "avencores_githubmirror_26",
#     "https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/refs/heads/main/githubmirror/26.txt",
# ),
# (
#     "avencores_01_openray_all_valid_proxies",
#     "https://github.com/sakha1370/OpenRay/raw/refs/heads/main/output/all_valid_proxies.txt",
# ),
# (
#     "avencores_02_sevcator_vl",
#     "https://raw.githubusercontent.com/sevcator/5ubscrpt10n/main/protocols/vl.txt",
# ),
# (
#     "avencores_03_yitong2333_v2ray",
#     "https://raw.githubusercontent.com/yitong2333/proxy-minging/refs/heads/main/v2ray.txt",
# ),
# (
#     "avencores_04_acymz_v2",
#     "https://raw.githubusercontent.com/acymz/AutoVPN/refs/heads/main/data/V2.txt",
# ),
# (
#     "avencores_05_miladtahanian_sub",
#     "https://raw.githubusercontent.com/miladtahanian/V2RayCFGDumper/refs/heads/main/sub.txt",
# ),
# (
#     "avencores_06_roosterkid_v2ray_raw",
#     "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
# ),
# (
#     "avencores_07_epodonios_trojan",
#     "https://github.com/Epodonios/v2ray-configs/raw/main/Splitted-By-Protocol/trojan.txt",
# ),
# (
#     "avencores_08_cidvpn_general",
#     "https://raw.githubusercontent.com/CidVpn/cid-vpn-config/refs/heads/main/general.txt",
# ),
# (
#     "avencores_09_mohamadfg_vless",
#     "https://raw.githubusercontent.com/mohamadfg-dev/telegram-v2ray-configs-collector/refs/heads/main/category/vless.txt",
# ),
# (
#     "avencores_10_mheidari98_proxy_vless",
#     "https://raw.githubusercontent.com/mheidari98/.proxy/refs/heads/main/vless",
# ),
# (
#     "avencores_11_youfoundamin_mixed_iran",
#     "https://raw.githubusercontent.com/youfoundamin/V2rayCollector/main/mixed_iran.txt",
# ),
# (
#     "avencores_12_expressalaki_configs3",
#     "https://raw.githubusercontent.com/expressalaki/ExpressVPN/refs/heads/main/configs3.txt",
# ),
# (
#     "avencores_13_mahsanetconfig_xray_final",
#     "https://raw.githubusercontent.com/MahsaNetConfigTopic/config/refs/heads/main/xray_final.txt",
# ),
# (
#     "avencores_14_lalatinahub_nodes",
#     "https://github.com/LalatinaHub/Mineral/raw/refs/heads/master/result/nodes",
# ),
# (
#     "avencores_15_miladtahanian_config_collector",
#     "https://raw.githubusercontent.com/miladtahanian/Config-Collector/refs/heads/main/mixed_iran.txt",
# ),
# (
#     "avencores_16_pawdroid_sub",
#     "https://raw.githubusercontent.com/Pawdroid/Free-servers/refs/heads/main/sub",
# ),
# (
#     "avencores_17_mhditaheri_mix",
#     "https://github.com/MhdiTaheri/V2rayCollector_Py/raw/refs/heads/main/sub/Mix/mix.txt",
# ),
# (
#     "avencores_18_free18_v",
#     "https://raw.githubusercontent.com/free18/v2ray/refs/heads/main/v.txt",
# ),
# (
#     "avencores_19_mhditaheri_sub_mix",
#     "https://github.com/MhdiTaheri/V2rayCollector/raw/refs/heads/main/sub/mix",
# ),
# (
#     "avencores_20_argh94_all_config",
#     "https://github.com/Argh94/Proxy-List/raw/refs/heads/main/All_Config.txt",
# ),
# (
#     "avencores_21_shabane_merged",
#     "https://raw.githubusercontent.com/shabane/kamaji/master/hub/merged.txt",
# ),
# (
#     "avencores_22_wuqb2i4f_mix_uri",
#     "https://raw.githubusercontent.com/wuqb2i4f/xray-config-toolkit/main/output/base64/mix-uri",
# ),
# (
#     "avencores_23_whiteprime_available",
#     "https://raw.githubusercontent.com/WhitePrime/xraycheck/refs/heads/main/configs/available",
# ),
# (
#     "avencores_24_mr_meshky_vless",
#     "https://github.com/Mr-Meshky/vify/raw/refs/heads/main/configs/vless.txt",
# ),
# (
#     "avencores_25_v2rayroot_vless",
#     "https://raw.githubusercontent.com/V2RayRoot/V2RayConfig/refs/heads/main/Config/vless.txt",
# ),
# (
#     "avencores_extra_01_igareck_white_sni_all",
#     "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-SNI-RU-all.txt",
# ),
# (
#     "avencores_extra_02_zieng2_vless",
#     "https://raw.githubusercontent.com/zieng2/wl/main/vless.txt",
# ),
# (
#     "avencores_extra_03_zieng2_vless_universal",
#     "https://raw.githubusercontent.com/zieng2/wl/refs/heads/main/vless_universal.txt",
# ),
# (
#     "avencores_extra_04_zieng2_vless_lite",
#     "https://raw.githubusercontent.com/zieng2/wl/main/vless_lite.txt",
# ),
# (
#     "avencores_extra_05_etoneya_2",
#     "https://raw.githubusercontent.com/EtoNeYaProject/etoneyaproject.github.io/refs/heads/main/2",
# ),
# (
#     "avencores_extra_06_byewhitelists2",
#     "https://raw.githubusercontent.com/ByeWhiteLists/ByeWhiteLists2/refs/heads/main/ByeWhiteLists2.txt",
# ),
# (
#     "avencores_extra_07_whiteprime_white_list_available",
#     "https://whiteprime.github.io/xraycheck/configs/white-list_available",
# ),
# (
#     "avencores_extra_08_wlrus_selected",
#     "https://wlrus.lol/confs/selected.txt",
# ),
# (
#     "flexiy0_russia_whitelist",
#     "https://raw.githubusercontent.com/FLEXIY0/matryoshka-vpn/refs/heads/main/configs/russia_whitelist.txt",
# ),
# (
#     "epodonios_all_configs_sub",
#     "https://raw.githubusercontent.com/Epodonios/v2ray-configs/refs/heads/main/All_Configs_Sub.txt",
# ),
# (
#     "shatakvpn_ru_vless",
#     "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/refs/heads/main/configs/ru/vless.txt",
# ),
# (
#     "argh94_v2rayautoconfig_vless",
#     "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Vless.txt",
# ),
# (
#     "y9felix_r",
#     "https://raw.githubusercontent.com/y9felix/s/refs/heads/main/r",
# ),
# (
#     "kort0881_ru_white_part1",
#     "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_part1.txt",
# ),
# (
#     "kort0881_ru_white_part2",
#     "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_part2.txt",
# ),
# (
#     "kort0881_ru_white_part3",
#     "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_part3.txt",
# ),
# (
#     "kort0881_ru_white_part4",
#     "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_part4.txt",
# ),
# (
#     "kort0881_ru_white_part5",
#     "https://raw.githubusercontent.com/kort0881/vpn-checker-backend/main/checked/RU_Best/ru_white_part5.txt",
# ),
# (
#     "ginolrewadsb11_bobi_vpn",
#     "https://raw.githubusercontent.com/ginolrewadsb11/studious-umbrella/main/bobi_vpn.txt",
# ),
# (
#     "sakha1370_openray_ru_pinned",
#     "https://raw.githubusercontent.com/sakha1370/OpenRay/fd98dbbea14ddd5912a93481659caaba565e45d4/output/country/RU.txt",
# ),
# (
#     "kiryascript_26",
#     "https://raw.githubusercontent.com/KiryaScript/white-lists/cf8bd3a525d1409539e60cae5430f82b58661f31/githubmirror/26.txt",
# ),
# (
#     "kiryascript_27",
#     "https://raw.githubusercontent.com/KiryaScript/white-lists/cf8bd3a525d1409539e60cae5430f82b58661f31/githubmirror/27.txt",
# ),
# (
#     "kiryascript_28",
#     "https://raw.githubusercontent.com/KiryaScript/white-lists/cf8bd3a525d1409539e60cae5430f82b58661f31/githubmirror/28.txt",
# ),
# (
#     "subrostunnel_wl",
#     "https://subrostunnel.vercel.app/wl.txt",
# ),

COUNTRY_WORD_RE = r"(?:[A-Z][A-Za-z\u00C0-\u017E']*|and|of|the)"
COUNTRY_FRAGMENT_RE = re.compile(
    rf"(?P<country>{COUNTRY_WORD_RE}(?:[ -]{COUNTRY_WORD_RE})*)(?=\s*(?:,|\||\[|$))"
)

MSK = timezone(timedelta(hours=3), name="MSK")
MAX_TCP_WORKERS = 20
TEST_TIMEOUT = 5
MAX_LATENCY_MS = 2000
UNSUPPORTED_TRANSPORTS = {"xhttp"}
SUPPORTED_TRANSPORTS = {"tcp", "ws", "grpc", "httpupgrade", "raw"}
UNSUPPORTED_SECURITIES = {"none", ""}


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
        "path": query.get("path", ""),
        "host": query.get("host", ""),
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
        transport = parse_vless_key(key)["transport"]
        counter[normalize_transport(transport)] += 1
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

        security = (parsed["security"] or "").strip().lower()
        if security in UNSUPPORTED_SECURITIES:
            unsupported_reasons["security_none"] += 1
            continue

        transport = normalize_transport(parsed["transport"])
        if transport in UNSUPPORTED_TRANSPORTS:
            unsupported_reasons[transport] += 1
            continue

        if transport not in SUPPORTED_TRANSPORTS:
            unsupported_reasons["unsupported_transport"] += 1
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
            endpoint = futures[future]
            endpoint_keys = endpoint_groups[endpoint]
            result = future.result()
            done += 1
            if on_result:
                on_result(done, total, result)

            for key in endpoint_keys:
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
