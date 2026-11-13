#!/usr/bin/env python3
"""Agente de concursos.

Busca concursos na concursosPublicosAPI (Vinimartinsc), descarta os que já foram
enviados e manda as novidades para o Telegram, junto com links de material de
consulta do PCI Concursos (apostilas, provas, simulados).

Só usa a biblioteca padrão do Python (nenhuma instalação necessária).
"""
import argparse
import html
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib import error, parse, request

PCI = "https://www.pciconcursos.com.br"
SITE_BASE = os.environ.get("SITE_BASE", "https://concursosnobrasil.com").rstrip("/")
TELEGRAM_LIMIT = 3900  # o limite do Telegram é 4096 caracteres por mensagem
STATUS_LABEL = {
    "open": ("🟢", "Aberto"),
    "expected": ("🟡", "Previsto"),
    "closed": ("🔴", "Encerrado"),
}
USER_AGENT = "concursos-bot/1.0"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------------
def env_list(name, default):
    raw = os.environ.get(name, default)
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def load_config():
    return {
        "token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "api_url": os.environ.get("CONCURSOS_API_URL", "http://127.0.0.1:5000").rstrip("/"),
        "ufs": env_list("UFS", "rj,br"),
        "statuses": env_list("STATUSES", "open"),
        "keywords": env_list("KEYWORDS", ""),
        "max_per_uf": int(os.environ.get("MAX_PER_UF", "20")),
        "state_file": Path(os.environ.get("STATE_FILE", "state/seen.json")),
        "first_run_send": os.environ.get("FIRST_RUN_SEND", "0") == "1",
    }


# ----------------------------------------------------------------------------
# Fonte de concursos (concursosPublicosAPI)
# ----------------------------------------------------------------------------
def http_get_json(url, retries=3, timeout=45):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = request.Request(url, headers={"User-Agent": USER_AGENT})
            with request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"falha ao consultar {url}: {last}")


class _RowParser(HTMLParser):
    """Extrai as linhas de tabela: primeiro link e texto de cada célula.

    Não depende de nomes de classe CSS, que é o que costuma quebrar scrapers.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = {"href": None, "cells": []}
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "a" and self._row is not None and self._row["href"] is None:
            self._row["href"] = dict(attrs).get("href")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row["cells"].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def fetch_direct(uf):
    """Lê a tabela de concursos direto do ConcursosNoBrasil (plano B da API)."""
    url = f"{SITE_BASE}/concursos/{uf}/"
    req = request.Request(
        url,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9",
        },
    )
    try:
        with request.urlopen(req, timeout=45) as resp:
            status, raw = resp.status, resp.read()
    except error.HTTPError as exc:
        raise RuntimeError(f"site respondeu HTTP {exc.code} em {url} (possível bloqueio do IP do servidor)") from None
    except error.URLError as exc:
        raise RuntimeError(f"falha de rede ao abrir {url}: {exc.reason}") from None

    text = raw.decode("utf-8", errors="replace")
    parser = _RowParser()
    parser.feed(text)
    items = []
    for row in parser.rows:
        href, cells = row["href"], row["cells"]
        if not href or href.startswith("#") or len(cells) < 2:
            continue
        status_txt = "expected" if re.search(r"previsto", cells[0], re.I) else "open"
        org = re.sub(r"\s*previsto\s*$", "", cells[0], flags=re.I).strip()
        if not org:
            continue
        items.append(
            {
                "link": parse.urljoin(url, href),
                "organization": org,
                "vagas": cells[1],
                "status": status_txt,
            }
        )
    if not items:
        title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        title = " ".join(title.group(1).split())[:80] if title else "sem título"
        raise RuntimeError(
            f"nenhuma linha de concurso encontrada em {url} "
            f"(HTTP {status}, {len(raw)} bytes, {len(parser.rows)} linhas de tabela, título: {title!r})"
        )
    return items


def fetch_concursos(api_url, uf):
    """Tenta a API; se ela falhar, lê o site direto."""
    try:
        return fetch_from_api(api_url, uf)
    except RuntimeError as exc:
        log(f"[{uf}] API falhou ({str(exc)[:120]}); lendo o site direto")
        return fetch_direct(uf)


def fetch_from_api(api_url, uf):
    data = http_get_json(f"{api_url}/concursos/{uf}")
    if not isinstance(data, list):
        raise RuntimeError(f"resposta inesperada da API para '{uf}': {str(data)[:120]}")
    items = []
    for raw in data:
        link = (raw.get("link") or "").strip()
        if not link:
            continue
        items.append(
            {
                "link": parse.urljoin(SITE_BASE + "/", link),
                "organization": (raw.get("organization") or "Sem nome").strip(),
                "vagas": str(raw.get("workPlacesAvailable") or "").strip(),
                "status": (raw.get("status") or "open").strip().lower(),
            }
        )
    return items


def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def passes_filters(item, cfg):
    if cfg["statuses"] and item["status"] not in cfg["statuses"]:
        return False
    if cfg["keywords"]:
        org = normalize(item["organization"])
        if not any(normalize(k) in org for k in cfg["keywords"]):
            return False
    return True


# ----------------------------------------------------------------------------
# Material de consulta (PCI Concursos) - links diretos, sem extrair conteúdo
# ----------------------------------------------------------------------------
def uf_label(uf):
    return "Nacional" if uf == "br" else uf.upper()


def pci_links(uf):
    region = "nacional" if uf == "br" else uf
    return [
        (f"Concursos {uf_label(uf)}", f"{PCI}/concursos/{region}/"),
        ("Apostilas", f"{PCI}/apostilas/"),
        ("Provas", f"{PCI}/provas/"),
        ("Simulados", f"{PCI}/simulados/"),
    ]


# ----------------------------------------------------------------------------
# Mensagens
# ----------------------------------------------------------------------------
def format_item(item):
    emoji, label = STATUS_LABEL.get(item["status"], ("⚪", item["status"]))
    vagas = f"Vagas: {html.escape(item['vagas'])} · " if item["vagas"] else ""
    href = html.escape(item["link"], quote=True)
    return (
        f"\n{emoji} <b>{html.escape(item['organization'])}</b>\n"
        f"{vagas}{label}\n"
        f'<a href="{href}">Ver concurso</a>\n'
    )


def build_messages(uf, items):
    header = f"📢 <b>Novos concursos — {uf_label(uf)}</b>\n"
    links = " · ".join(
        f'<a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
        for title, url in pci_links(uf)
    )
    footer = f"\n📚 <b>Material de consulta (PCI)</b>\n{links}"
    messages, current = [], header
    for item in items:
        block = format_item(item)
        if len(current) + len(block) + len(footer) > TELEGRAM_LIMIT:
            messages.append(current.rstrip())
            current = header + "<i>(continuação)</i>\n"
        current += block
    messages.append(current + footer)
    return messages


# ----------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------
def telegram_call(token, method, payload=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload or {}).encode()
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
    except error.HTTPError as exc:  # não imprime a URL: ela contém o token
        detail = exc.read().decode(errors="replace")[:200]
        raise RuntimeError(f"Telegram respondeu HTTP {exc.code}: {detail}") from None
    except error.URLError as exc:
        raise RuntimeError(f"falha de rede ao falar com o Telegram: {exc.reason}") from None
    if not body.get("ok"):
        raise RuntimeError(f"Telegram recusou a chamada: {body}")
    return body["result"]


def telegram_sender(cfg):
    def send(text):
        telegram_call(
            cfg["token"],
            "sendMessage",
            {
                "chat_id": cfg["chat_id"],
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )

    return send


def print_chat_ids(token):
    updates = telegram_call(token, "getUpdates")
    chats = {}
    for upd in updates:
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("title") or chat.get("first_name") or ""
    if not chats:
        print("Nenhuma conversa encontrada. Mande uma mensagem qualquer ao seu bot e rode de novo.")
    for chat_id, name in chats.items():
        print(f"chat_id={chat_id}  ({name})")


# ----------------------------------------------------------------------------
# Estado (links já enviados)
# ----------------------------------------------------------------------------
def load_state(path):
    if not path.exists():
        return {}, True
    try:
        return json.loads(path.read_text(encoding="utf-8")), False
    except json.JSONDecodeError:
        log(f"aviso: {path} corrompido; recomeçando do zero")
        return {}, True


def save_state(path, state):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    state = {link: ts for link, ts in state.items() if ts >= cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------------------------------
# Execução
# ----------------------------------------------------------------------------
def run(cfg, send, persist=True):
    """Retorna o número de falhas (0 = tudo certo)."""
    state, first_run = load_state(cfg["state_file"])
    now = datetime.now(timezone.utc).isoformat()
    failures = 0
    found = {}

    for uf in cfg["ufs"]:
        try:
            items = [i for i in fetch_concursos(cfg["api_url"], uf) if passes_filters(i, cfg)]
        except RuntimeError as exc:
            log(f"[{uf}] {exc}")
            failures += 1
            continue
        found[uf] = items
        log(f"[{uf}] {len(items)} concursos após os filtros")

    if failures == len(cfg["ufs"]):
        log("nenhuma UF pôde ser consultada; nada foi enviado")
        return failures

    if first_run and not cfg["first_run_send"]:
        total = 0
        for items in found.values():
            for item in items:
                state[item["link"]] = now
                total += 1
        send(
            "✅ <b>Agente de concursos ativo.</b>\n"
            f"Estou monitorando {total} concursos ({', '.join(uf_label(u) for u in found)}). "
            "A partir de agora você recebe só os novos."
        )
        if persist:
            save_state(cfg["state_file"], state)
        return failures

    for uf, items in found.items():
        fresh, seen_now = [], set()
        for item in items:
            if item["link"] not in state and item["link"] not in seen_now:
                fresh.append(item)
                seen_now.add(item["link"])
        fresh = fresh[: cfg["max_per_uf"]]
        if not fresh:
            continue
        try:
            for message in build_messages(uf, fresh):
                send(message)
        except RuntimeError as exc:
            log(f"[{uf}] envio falhou: {exc}")
            failures += 1
            break  # não marca como enviado; tenta de novo na próxima execução
        for item in fresh:
            state[item["link"]] = now
        log(f"[{uf}] {len(fresh)} novos enviados")

    if persist:
        save_state(cfg["state_file"], state)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="imprime as mensagens em vez de enviar (não altera o estado)")
    parser.add_argument("--chat-id", action="store_true", help="mostra o chat_id das conversas com o seu bot")
    args = parser.parse_args()
    cfg = load_config()

    if args.chat_id:
        if not cfg["token"]:
            sys.exit("defina TELEGRAM_BOT_TOKEN")
        print_chat_ids(cfg["token"])
        return

    dry = args.dry_run or os.environ.get("DRY_RUN") == "1"
    if dry:
        def send(text):
            print("-" * 60)
            print(text)
    else:
        if not cfg["token"] or not cfg["chat_id"]:
            sys.exit("defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID")
        send = telegram_sender(cfg)

    failures = run(cfg, send, persist=not dry)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
