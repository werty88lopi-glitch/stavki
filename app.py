"""
Калькулятор ставки: сайт + автоматический курс евро с ЦБ РФ.

Маршруты:
  /        — страница калькулятора (index.html из той же папки)
  /eur     — JSON с курсом евро, обновляется не чаще раза в 24 часа

Запуск локально:  python app.py   и открыть http://localhost:8000
На хостинге сервер сам читает порт из переменной PORT.
Только стандартная библиотека Python, ничего устанавливать не нужно.
"""
import json
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
DAY = 24 * 3600
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

cache = {"eur": None, "date": None, "ts": 0.0}


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


def get_eur():
    """Возвращает курс из кэша, обновляя его раз в сутки."""
    if cache["eur"] is None or time.time() - cache["ts"] >= DAY:
        try:
            cache["eur"], cache["date"] = fetch_eur()
            cache["ts"] = time.time()
        except Exception as e:
            if cache["eur"] is None:
                raise
            print("Не удалось обновить курс, используем сохранённый:", e)
    return cache


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

        if path in ("", "/index.html"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return

        if path == "/eur":
            try:
                c = get_eur()
                self._json(200, {
                    "eur": c["eur"],
                    "date": c["date"],
                    "fetched_at": int(c["ts"] * 1000),
                })
            except Exception as e:
                self._json(503, {"error": str(e)})
            return

        self._json(404, {"error": "not found"})

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0"
    print(f"Сервер запущен на порту {port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
