"""Генерация xray config.json из переменной VLESS_URL.

Запускается как init-контейнер при старте стека, записывает конфиг
в shared volume, после чего завершается. Xray читает готовый файл.
"""
import json
import os
import sys
from urllib.parse import parse_qs, unquote, urlparse

VLESS_URL = os.environ.get("VLESS_URL", "").strip()
OUTPUT = os.environ.get("OUTPUT_PATH", "/xray-config/config.json")

if not VLESS_URL:
    print("ERROR: VLESS_URL не задан", file=sys.stderr)
    sys.exit(1)

url = VLESS_URL.split("#")[0]
parsed = urlparse(url)
params = parse_qs(parsed.query)


def get(key: str, default: str = "") -> str:
    return unquote(params.get(key, [default])[0])


uuid = parsed.username
host = parsed.hostname
port = parsed.port
transport = get("type", "tcp")
security = get("security", "none")
flow = get("flow", "")

stream: dict = {"network": transport}

if security == "reality":
    stream["security"] = "reality"
    stream["realitySettings"] = {
        "serverName": get("sni"),
        "fingerprint": get("fp", "chrome"),
        "publicKey": get("pbk"),
        "shortId": get("sid"),
        "spiderX": get("spx", "/"),
    }
elif security == "tls":
    stream["security"] = "tls"
    stream["tlsSettings"] = {
        "serverName": get("sni"),
        "fingerprint": get("fp", "chrome"),
    }

if transport == "ws":
    ws: dict = {"path": get("path", "/")}
    if get("host"):
        ws["headers"] = {"Host": get("host")}
    stream["wsSettings"] = ws

elif transport == "xhttp":
    xhttp: dict = {"path": get("path", "/"), "mode": get("mode", "auto")}
    if get("host"):
        xhttp["host"] = get("host")
    stream["xhttpSettings"] = xhttp

elif transport == "grpc":
    stream["grpcSettings"] = {"serviceName": get("path", "").lstrip("/")}

config = {
    "log": {"loglevel": "warning"},
    "inbounds": [
        {
            "port": 1080,
            "listen": "0.0.0.0",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True},
        }
    ],
    "outbounds": [
        {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": host,
                        "port": port,
                        "users": [
                            {"id": uuid, "encryption": "none", "flow": flow}
                        ],
                    }
                ]
            },
            "streamSettings": stream,
        },
        {"tag": "direct", "protocol": "freedom"},
    ],
    "routing": {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            {
                "type": "field",
                "domain": ["api.telegram.org"],
                "outboundTag": "proxy",
            }
        ],
    },
}

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w") as f:
    json.dump(config, f, indent=2)

print(f"Config written to {OUTPUT} (host={host}:{port}, transport={transport}, security={security})")
