#!/usr/bin/env python3
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from vless_utils import normalize_transport, parse_vless_key

SINGBOX_TEST_URL = "https://www.gstatic.com/generate_204"
SINGBOX_HTTP_TIMEOUT = 8
SINGBOX_PORT_TIMEOUT = 4
MAX_SINGBOX_WORKERS = max(1, int(os.environ.get("SINGBOX_WORKERS", "12")))


def resolve_singbox_binary():
    env_path = os.environ.get("SING_BOX_BIN")
    if env_path and os.path.exists(env_path):
        return env_path

    path_binary = shutil.which("sing-box")
    if path_binary:
        return path_binary

    return None


def allocate_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port, timeout=SINGBOX_PORT_TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def build_tls_config(parsed):
    security = parsed["security"]
    if security not in {"tls", "reality"}:
        return None

    tls_config = {
        "enabled": True,
        "server_name": parsed["sni"] or parsed["server"],
        "insecure": False,
    }

    fingerprint = parsed["fingerprint"]
    if fingerprint:
        tls_config["utls"] = {
            "enabled": True,
            "fingerprint": fingerprint,
        }

    if security == "reality":
        if not parsed["public_key"]:
            return None
        tls_config["reality"] = {
            "enabled": True,
            "public_key": parsed["public_key"],
            "short_id": parsed["short_id"],
        }

    return tls_config


def build_transport_config(parsed):
    transport = normalize_transport(parsed["transport"])
    host_header = parsed["host"] or parsed["sni"] or parsed["server"]
    path = parsed["path"] or "/"

    if transport == "tcp":
        return None

    if transport == "ws":
        return {
            "type": "ws",
            "path": path,
            "headers": {
                "Host": host_header,
            },
        }

    if transport == "grpc":
        return {
            "type": "grpc",
            "service_name": parsed["service_name"] or "",
        }

    if transport == "httpupgrade":
        return {
            "type": "httpupgrade",
            "host": host_header,
            "path": path,
        }

    return None


def build_singbox_config(key, local_port):
    parsed = parse_vless_key(key)
    tls_config = build_tls_config(parsed)
    if not tls_config:
        raise ValueError("unsupported_security")

    outbound = {
        "type": "vless",
        "tag": "proxy",
        "server": parsed["server"],
        "server_port": parsed["server_port"],
        "uuid": parsed["uuid"],
        "tls": tls_config,
    }

    if parsed["flow"]:
        outbound["flow"] = parsed["flow"]

    if parsed["packet_encoding"]:
        outbound["packet_encoding"] = parsed["packet_encoding"]

    transport = build_transport_config(parsed)
    if transport:
        outbound["transport"] = transport

    return {
        "log": {
            "level": "error",
        },
        "inbounds": [
            {
                "type": "socks",
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "listen_port": local_port,
            }
        ],
        "outbounds": [
            outbound,
            {
                "type": "direct",
                "tag": "direct",
            },
        ],
        "route": {
            "final": "proxy",
        },
    }


def cleanup_process(process):
    if not process:
        return
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            return


def probe_through_socks(local_port):
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--socks5-hostname",
        f"127.0.0.1:{local_port}",
        "--connect-timeout",
        "4",
        "--max-time",
        str(SINGBOX_HTTP_TIMEOUT),
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code} %{time_total}",
        SINGBOX_TEST_URL,
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None, "probe"

    output = completed.stdout.strip().split()
    if len(output) != 2:
        return None, "probe"

    http_code, time_total = output
    if http_code != "204":
        return None, f"http_{http_code}"

    try:
        latency_ms = round(float(time_total) * 1000, 1)
    except ValueError:
        return None, "probe"

    return latency_ms, None


def test_key_singbox(key, singbox_binary):
    try:
        parsed = parse_vless_key(key)
    except ValueError:
        return {
            "status": "error",
            "key": key,
            "host": None,
            "port": None,
            "reason": "invalid",
        }

    host = parsed["server"]
    port = parsed["server_port"]
    local_port = allocate_local_port()
    process = None
    config_path = None

    try:
        config = build_singbox_config(key, local_port)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(config, tmp, ensure_ascii=False)
            config_path = tmp.name

        process = subprocess.Popen(
            [singbox_binary, "run", "-c", config_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if not wait_for_port(local_port):
            return {
                "status": "error",
                "key": key,
                "host": host,
                "port": port,
                "reason": "singbox_ready",
            }

        latency_ms, error_reason = probe_through_socks(local_port)
        if error_reason:
            return {
                "status": "error",
                "key": key,
                "host": host,
                "port": port,
                "reason": error_reason,
            }

        return {
            "status": "ok",
            "key": key,
            "host": host,
            "port": port,
            "latency_ms": latency_ms,
        }
    except ValueError as error:
        return {
            "status": "error",
            "key": key,
            "host": host,
            "port": port,
            "reason": str(error),
        }
    except OSError:
        return {
            "status": "error",
            "key": key,
            "host": host,
            "port": port,
            "reason": "singbox_start",
        }
    finally:
        cleanup_process(process)
        if config_path and os.path.exists(config_path):
            os.remove(config_path)


def run_singbox_checks(keys, on_result=None):
    singbox_binary = resolve_singbox_binary()
    if not singbox_binary:
        raise RuntimeError("sing-box binary not found")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_SINGBOX_WORKERS) as executor:
        futures = {executor.submit(test_key_singbox, key, singbox_binary): key for key in keys}
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
