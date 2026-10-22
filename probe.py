#!/usr/bin/env python3
"""Реальная проверка VLESS-конфигов: Xray поднимает туннель, через него идёт HTTP-запрос.

TCP-коннект до host:port ничего не доказывает — порт отвечает почти всегда.
Здесь проверяется весь путь: TLS/REALITY-хендшейк, авторизация по UUID,
транспорт и выход в интернет с сервера.
"""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import vless_uri

BATCH_SIZE = int(os.environ.get("PROBE_BATCH_SIZE", "50"))
BASE_PORT = int(os.environ.get("PROBE_BASE_PORT", "21080"))
REQUEST_TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "12"))
MAX_PARALLEL = int(os.environ.get("PROBE_PARALLEL", "25"))
RETRIES = int(os.environ.get("PROBE_RETRIES", "2"))
XRAY_BOOT_TIMEOUT = 20.0
# Коды curl → понятные причины отказа.
CURL_REASONS = {
    5: "proxy_error",
    7: "connect_failed",
    28: "timeout",
    35: "tls_handshake",
    52: "empty_reply",
    56: "recv_error",
    97: "proxy_error",
}
TEST_URLS = [
    "https://www.gstatic.com/generate_204",
    "https://cp.cloudflare.com/generate_204",
]


class XrayMissing(RuntimeError):
    pass


def find_xray():
    explicit = os.environ.get("XRAY_BIN")
    if explicit and os.access(explicit, os.X_OK):
        return explicit
    for candidate in ("./xray", "./xraybin/xray"):
        if os.access(candidate, os.X_OK):
            return os.path.abspath(candidate)
    found = shutil.which("xray")
    if found:
        return found
    raise XrayMissing(
        "Не найден бинарник xray. Укажите путь в XRAY_BIN или положите ./xray"
    )


def _build_batch_config(configs, base_port):
    inbounds, outbounds, rules = [], [], []
    for offset, config in enumerate(configs):
        tag = f"p{offset}"
        inbounds.append(
            {
                "tag": f"in-{tag}",
                "listen": "127.0.0.1",
                "port": base_port + offset,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": False},
                "sniffing": {"enabled": False},
            }
        )
        outbounds.append(vless_uri.to_outbound(config, f"out-{tag}"))
        rules.append(
            {
                "type": "field",
                "inboundTag": [f"in-{tag}"],
                "outboundTag": f"out-{tag}",
            }
        )
    outbounds.append({"tag": "block", "protocol": "blackhole"})
    return {
        "log": {"loglevel": "error"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {"domainStrategy": "AsIs", "rules": rules},
    }


def _wait_for_port(port, deadline):
    while time.time() < deadline:
        with socket.socket() as probe_socket:
            probe_socket.settimeout(0.5)
            if probe_socket.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _probe_once(port, url):
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--output",
        os.devnull,
        "--socks5-hostname",
        f"127.0.0.1:{port}",
        "--max-time",
        str(REQUEST_TIMEOUT),
        "--write-out",
        "%{http_code} %{time_total}",
        url,
    ]
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT + 5,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}

    stdout = (completed.stdout or "").strip().split()
    if completed.returncode != 0 or len(stdout) != 2:
        code = completed.returncode
        return {"ok": False, "reason": CURL_REASONS.get(code, f"curl{code}")}

    http_code, time_total = stdout
    if http_code not in {"200", "204"}:
        return {"ok": False, "reason": f"http{http_code}"}

    try:
        latency_ms = round(float(time_total) * 1000, 1)
    except ValueError:
        latency_ms = round((time.time() - started) * 1000, 1)
    return {"ok": True, "latency_ms": latency_ms}


def _probe_slot(port):
    last = {"ok": False, "reason": "unknown"}
    for attempt in range(RETRIES):
        last = _probe_once(port, TEST_URLS[attempt % len(TEST_URLS)])
        if last["ok"]:
            return last
        time.sleep(0.3)
    return last


def _run_batch(xray_bin, configs, base_port, workdir):
    config_path = os.path.join(workdir, "xray.json")
    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(_build_batch_config(configs, base_port), file)

    log_path = os.path.join(workdir, "xray.log")
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [xray_bin, "run", "-c", config_path],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    try:
        if not _wait_for_port(base_port, time.time() + XRAY_BOOT_TIMEOUT):
            with open(log_path, "r", encoding="utf-8") as log_file:
                tail = log_file.read()[-400:].replace("\n", " ")
            return [{"ok": False, "reason": "xray_boot"} for _ in configs], tail

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
            results = list(
                executor.map(
                    _probe_slot, [base_port + offset for offset in range(len(configs))]
                )
            )
        return results, None
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _check_batch(xray_bin, batch):
    """Проверить партию. Если Xray не поднялся — делим партию пополам.

    Xray отказывается стартовать целиком из-за одного некорректного outbound,
    поэтому один битый конфиг не должен утягивать за собой остальные.
    """
    with tempfile.TemporaryDirectory(prefix="vless-probe-") as workdir:
        results, error = _run_batch(xray_bin, batch, BASE_PORT, workdir)

    if error is None or len(batch) == 1:
        return results, error

    middle = len(batch) // 2
    left_results, left_error = _check_batch(xray_bin, batch[:middle])
    right_results, right_error = _check_batch(xray_bin, batch[middle:])
    return left_results + right_results, left_error or right_error


def check_configs(configs, on_batch=None):
    """Проверить конфиги по-настоящему. Возвращает список результатов в том же порядке."""
    xray_bin = find_xray()
    results = []
    total = len(configs)

    for start in range(0, total, BATCH_SIZE):
        batch = configs[start:start + BATCH_SIZE]
        batch_results, error = _check_batch(xray_bin, batch)
        results.extend(batch_results)
        if on_batch:
            on_batch(min(start + len(batch), total), total, batch_results, error)

    return results
