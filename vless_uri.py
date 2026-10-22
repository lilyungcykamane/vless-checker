#!/usr/bin/env python3
"""Разбор, нормализация и сборка VLESS-URI."""
import json
import re
from html import unescape as html_unescape
from urllib.parse import parse_qs, quote, unquote, urlsplit

REGIONAL_INDICATOR_START = 0x1F1E6
REGIONAL_INDICATOR_END = 0x1F1FF

FLAG_COUNTRY_NAMES = {
    "AE": "UAE", "AL": "Albania", "AM": "Armenia", "AT": "Austria",
    "AU": "Australia", "AZ": "Azerbaijan", "BE": "Belgium", "BG": "Bulgaria",
    "BR": "Brazil", "BY": "Belarus", "CA": "Canada", "CH": "Switzerland",
    "CN": "China", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "EE": "Estonia", "ES": "Spain", "FI": "Finland",
    "FR": "France", "GB": "United Kingdom", "GE": "Georgia", "GR": "Greece",
    "HK": "Hong Kong", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IN": "India", "IR": "Iran", "IS": "Iceland",
    "IT": "Italy", "JP": "Japan", "KG": "Kyrgyzstan", "KR": "South Korea",
    "KZ": "Kazakhstan", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "MD": "Moldova", "ME": "Montenegro", "MX": "Mexico", "MY": "Malaysia",
    "NL": "Netherlands", "NO": "Norway", "NZ": "New Zealand", "PL": "Poland",
    "PT": "Portugal", "RO": "Romania", "RS": "Serbia", "RU": "Russia",
    "SA": "Saudi Arabia", "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia",
    "SK": "Slovakia", "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan",
    "UA": "Ukraine", "US": "United States", "UZ": "Uzbekistan",
    "VN": "Vietnam", "ZA": "South Africa",
}

UNKNOWN_COUNTRY = "Unknown"
UNKNOWN_FLAG = "🏴"


def find_first_flag_emoji(text):
    if not text:
        return None
    for index in range(len(text) - 1):
        first, second = ord(text[index]), ord(text[index + 1])
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


def normalize_transport(transport):
    normalized = (transport or "raw").strip().lower()
    if normalized in {"tcp", "raw", ""}:
        return "raw"
    if normalized == "splithttp":
        return "xhttp"
    return normalized


def parse(uri):
    """vless://... -> dict или None, если URI не разбирается."""
    uri = html_unescape(uri.strip())
    if not uri.startswith("vless://"):
        return None

    try:
        parsed = urlsplit(uri)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None

    if not parsed.username or not host or not port:
        return None

    query = {
        name: values[-1]
        for name, values in parse_qs(parsed.query, keep_blank_values=True).items()
    }
    fragment = unquote(parsed.fragment or "")
    flag = find_first_flag_emoji(fragment)
    country_code = flag_emoji_to_country_code(flag)

    insecure = (
        query.get("allowInsecure")
        or query.get("allowinsecure")
        or query.get("insecure")
        or ""
    ).strip().lower() in {"1", "true", "yes"}

    return {
        "uuid": parsed.username,
        "host": host.lower(),
        "port": int(port),
        "transport": normalize_transport(query.get("type")),
        "security": (query.get("security") or "none").strip().lower(),
        "sni": (query.get("sni") or query.get("serverName") or "").strip(),
        "http_host": (query.get("host") or "").strip(),
        "path": query.get("path") or "",
        "mode": (query.get("mode") or "").strip().lower(),
        "extra": query.get("extra") or "",
        "alpn": [item for item in (query.get("alpn") or "").split(",") if item],
        "fingerprint": (query.get("fp") or "chrome").strip().lower(),
        "public_key": (query.get("pbk") or "").strip(),
        "short_id": (query.get("sid") or "").strip(),
        "spider_x": query.get("spx") or "",
        "flow": (query.get("flow") or "").strip(),
        "header_type": (query.get("headerType") or "").strip().lower(),
        "service_name": (query.get("serviceName") or "").strip(),
        "packet_encoding": (query.get("packetEncoding") or "").strip(),
        "encryption": (query.get("encryption") or "none").strip(),
        "insecure": insecure,
        "country_code": country_code,
        "country": FLAG_COUNTRY_NAMES.get(country_code, UNKNOWN_COUNTRY),
        "flag": flag or UNKNOWN_FLAG,
        "raw_name": fragment,
    }


def identity(config):
    """Ключ дедупликации: одинаковая точка входа и одинаковый транспорт."""
    return (
        config["uuid"],
        config["host"],
        config["port"],
        config["transport"],
        config["security"],
        config["sni"],
        config["http_host"],
        config["path"],
        config["public_key"],
        config["short_id"],
    )


def endpoint(config):
    return f"{config['host']}:{config['port']}"


def to_uri(config, name):
    """Собрать URI обратно — с унифицированным именем и без мусорных параметров."""
    query = [("encryption", config["encryption"] or "none")]
    query.append(("type", config["transport"]))
    query.append(("security", config["security"]))

    if config["transport"] == "xhttp":
        if config["path"]:
            query.append(("path", config["path"]))
        if config["http_host"]:
            query.append(("host", config["http_host"]))
        if config["mode"]:
            query.append(("mode", config["mode"]))
        if config["extra"]:
            query.append(("extra", config["extra"]))
    elif config["header_type"]:
        query.append(("headerType", config["header_type"]))

    if config["security"] == "reality":
        query.append(("pbk", config["public_key"]))
        if config["short_id"]:
            query.append(("sid", config["short_id"]))
        if config["spider_x"]:
            query.append(("spx", config["spider_x"]))
    if config["alpn"]:
        query.append(("alpn", ",".join(config["alpn"])))
    if config["sni"]:
        query.append(("sni", config["sni"]))
    query.append(("fp", config["fingerprint"]))
    if config["flow"]:
        query.append(("flow", config["flow"]))
    if config["packet_encoding"]:
        query.append(("packetEncoding", config["packet_encoding"]))

    encoded = "&".join(
        f"{key}={quote(str(value), safe='')}" for key, value in query if value != ""
    )
    return (
        f"vless://{config['uuid']}@{config['host']}:{config['port']}"
        f"?{encoded}#{quote(name, safe='')}"
    )


def to_outbound(config, tag):
    """Исходящий Xray-outbound для реальной проверки конфига."""
    stream = {
        "network": config["transport"],
        "security": "none" if config["security"] == "none" else config["security"],
    }

    if config["security"] == "reality":
        stream["realitySettings"] = {
            "serverName": config["sni"],
            "fingerprint": config["fingerprint"],
            "publicKey": config["public_key"],
            "shortId": config["short_id"],
            "spiderX": config["spider_x"] or "/",
        }
    elif config["security"] == "tls":
        tls = {
            "serverName": config["sni"] or config["http_host"] or config["host"],
            "fingerprint": config["fingerprint"],
            "allowInsecure": config["insecure"],
        }
        if config["alpn"]:
            tls["alpn"] = config["alpn"]
        stream["tlsSettings"] = tls

    if config["transport"] == "xhttp":
        xhttp = {"path": config["path"] or "/"}
        if config["http_host"]:
            xhttp["host"] = config["http_host"]
        if config["mode"]:
            xhttp["mode"] = config["mode"]
        extra = config["extra"]
        if extra:
            try:
                parsed_extra = json.loads(extra)
                if isinstance(parsed_extra, dict):
                    xhttp["extra"] = parsed_extra
            except (TypeError, ValueError):
                pass
        stream["xhttpSettings"] = xhttp
    elif config["transport"] == "raw" and config["header_type"] == "http":
        stream["rawSettings"] = {"header": {"type": "http"}}

    user = {
        "id": config["uuid"],
        "encryption": config["encryption"] or "none",
    }
    if config["flow"]:
        user["flow"] = config["flow"]

    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": config["host"],
                    "port": config["port"],
                    "users": [user],
                }
            ]
        },
        "streamSettings": stream,
    }
