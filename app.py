"""
Калькулятор ставки: сайт + автоматические курсы.

Маршруты:
  /      — страница калькулятора (index.html из той же папки)
  /eur   — курс евро с ЦБ РФ, обновляется раз в 24 часа
  /jpy   — курс иены с сайта АТБ (продажа, ₽ за 100 ¥), обновляется раз в 24 часа
"""
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
ATB_URL = "https://www.atb.su/services/exchange/"
DAY = 24 * 3600
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

cache_eur = {"value": None, "date": None, "ts": 0.0}
cache_jpy = {"value": None, "ts": 0.0}


def fetch_eur():
    with urllib.request.urlopen(CBR_URL, timeout=15) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    for valute in root.iter("Valute"):
        if valute.findtext("CharCode") == "EUR":
            value = float(valute.findtext("Value").replace(",", "."))
            nominal = float(valute.findtext("Nominal").replace(",", "."))
            return value / nominal, root.get("Date")
    raise RuntimeError("EUR не найден в ответе ЦБ")


def fetch_jpy():
    req = urllib.request.Request(ATB_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    # Берём первую строку «JPY за 100¥ покупка X продажа Y» — продажа = курс для покупки иены клиентом
    m = re.search(r"JPY за 100¥ покупка ([\d.,]+) продажа ([\d.,]+)", text)
    if not m:
        raise RuntimeError("курс JPY не найден на сайте АТБ")
    return float(m.group(2).replace(",", "."))


def get_eur():
    if cache_eur["value"] is None or time.time() - cache_eur["ts"] >= DAY:
        try:
            cache_eur["value"], cache_eur["date"] = fetch_eur()
            cache_eur["ts"] = time.time()
        except Exception as e:
            if cache_eur["value"] is None:
                raise
            print("Не удалось обновить евро, используем сохранённый:", e)
    return cache_eur


def get_jpy():
    if cache_jpy["value"] is None or time.time() - cache_jpy["ts"] >= DAY:
        try:
            cache_jpy["value"] = fetch_jpy()
            cache_jpy["ts"] = time.time()
        except Exception as e:
            if cache_jpy["value"] is None:
                raise
            print("Не удалось обновить иену, используем сохранённый:", e)
    return cache_jpy


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        static = {"/manifest.json": "application/manifest+json", "/icon.svg": "image/svg+xml"}
        if path in static:
            with open(os.path.join(BASE_DIR, path.lstrip("/")), "rb") as f:
                self._send(200, f.read(), static[path] + "; charset=utf-8")
            return

        if path in ("", "/index.html"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return

        try:
            if path == "/eur":
                c = get_eur()
                self._json(200, {"eur": c["value"], "date": c["date"], "fetched_at": int(c["ts"] * 1000)})
                return
            if path == "/jpy":
                c = get_jpy()
                self._json(200, {"jpy": c["value"], "fetched_at": int(c["ts"] * 1000)})
                return
        except Exception as e:
            self._json(503, {"error": str(e)})
            return

        self._json(404, {"error": "not found"})

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Сервер запущен на порту {port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
