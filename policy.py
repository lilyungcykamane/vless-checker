#!/usr/bin/env python3
"""Политика отбора: что вообще имеет смысл проверять и отдавать пользователю."""
import ipaddress
from collections import Counter

# raw (tcp) + REALITY — классика, устойчивая к DPI.
# xhttp над TLS к белому SNI — основной рабочий вариант при белых списках.
# Всё остальное (grpc, ws, httpupgrade, kcp, quic, h2) либо режется DPI,
# либо нестабильно на мобильных операторах.
ALLOWED_TRANSPORTS = {"raw", "xhttp"}
ALLOWED_SECURITY = {"reality", "tls"}

# Имя конфига: флаг всегда первым, чтобы работали фильтры по стране в клиентах.
NAME_TEMPLATE = "{flag} {country} #{index:02d}"


def is_routable_host(host):
    """Отсеять заглушки и локальные адреса: в апстримах встречаются конфиги на 0.0.0.0."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." in host  # домен

    return not (
        address.is_unspecified
        or address.is_loopback
        or address.is_private
        or address.is_reserved
        or address.is_multicast
        or address.is_link_local
    )


def filter_configs(configs):
    """Оставить только то, что соответствует политике. Возвращает (ok, причины отказа)."""
    accepted = []
    rejected = Counter()

    for config in configs:
        transport = config["transport"]
        security = config["security"]

        if not is_routable_host(config["host"]):
            rejected["unroutable_host"] += 1
            continue
        if security not in ALLOWED_SECURITY:
            rejected["security_" + (security or "empty")] += 1
            continue
        if config["insecure"]:
            rejected["allow_insecure"] += 1
            continue
        if transport not in ALLOWED_TRANSPORTS:
            rejected["transport_" + transport] += 1
            continue
        if security == "reality" and not config["public_key"]:
            rejected["reality_without_pbk"] += 1
            continue
        if security == "reality" and not config["sni"]:
            rejected["reality_without_sni"] += 1
            continue
        if security == "tls" and not (config["sni"] or config["http_host"]):
            rejected["tls_without_sni"] += 1
            continue

        accepted.append(config)

    return accepted, dict(rejected)


def assign_names(configs):
    """Унифицированное имя для каждого конфига: нумерация по стране в порядке рейтинга."""
    counters = Counter()
    for config in configs:
        country = config["country"]
        counters[country] += 1
        config["name"] = NAME_TEMPLATE.format(
            flag=config["flag"],
            country=country,
            index=counters[country],
        )
    return configs
