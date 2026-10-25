#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de lista M3U do SO Play (soplay.com.br) otimizada para SS IPTV.

Recursos:
  - Somente biblioteca padrao do Python (sem pip).
  - Categorias normalizadas: junta maiusc/minusc e sinonimos numa unica categoria.
  - Remove canais com o MESMO link (mantem apenas 1).
  - Reconciliacao com regra das 3 falhas: so remove um canal depois de 3
    atualizacoes seguidas sem funcionar (estado em estado_canais.json).
  - Protecao contra queda geral da fonte (nao penaliza canais se a fonte
    inteira ficar inacessivel).
  - Logging detalhado (vistos / incluidos / novos / removidos).

Variaveis de ambiente (todas opcionais):
  SOPLAY_API    URL do endpoint JSON de canais capturado no F12 > Network
                (quando o descobrimento automatico nao encontrar).
  SOPLAY_TOKEN  Token/Authorization capturado no F12 (se a API exigir).
  SOPLAY_CHECK  "1" para testar se cada .m3u8 responde (liveness).
                Deixe desligado quando rodar fora do Brasil (gera falso-negativo).
  SOPLAY_DEBUG  "1" para salvar respostas cruas em debug_soplay/.
"""

import json
import os
import re
import sys
import time
import unicodedata
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import request, error, parse

# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------
BASE_SITE   = "https://soplay.com.br"
OUT_DIR     = "playlists"
OUT_FILE    = os.path.join(OUT_DIR, "soplay.m3u")
STATE_FILE  = "estado_canais.json"
DEBUG_DIR   = "debug_soplay"

MAX_FALHAS  = 3            # remove apenas apos 3 atualizacoes sem funcionar
TIMEOUT     = 25
UA          = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0 Safari/537.36")

DEBUG = os.environ.get("SOPLAY_DEBUG") == "1"
CHECK = os.environ.get("SOPLAY_CHECK") == "1"


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------------
# Normalizacao / fusao de categorias (maiusc-minusc + sinonimos)
# --------------------------------------------------------------------------
# Cada grupo abaixo vira UMA unica categoria (o 1o item e o nome final exibido).
SINONIMOS = [
    ("Filmes",        ["filmes", "filme", "cinema", "movies", "movie", "cinemas"]),
    ("Series",        ["series", "serie", "seriados", "seriado", "tv shows", "shows"]),
    ("Infantil",      ["infantil", "infantis", "desenhos", "desenho", "kids", "kid",
                        "crianca", "criancas", "cartoon", "cartoons", "children",
                        "animacao", "animacoes", "anime", "animes"]),
    ("Noticias",      ["noticias", "noticia", "news", "jornalismo", "jornal",
                        "jornais"]),
    ("Esportes",      ["esportes", "esporte", "sports", "sport", "futebol",
                        "desporto"]),
    ("Musica",        ["musica", "musicas", "music", "musical", "clipes"]),
    ("Documentarios", ["documentarios", "documentario", "docs", "doc",
                        "documentary", "documentaries"]),
    ("Religiosos",    ["religiosos", "religioso", "religiao", "religiosa",
                        "gospel", "evangelico", "evangelicos", "catolico",
                        "catolicos", "fe", "cristao", "cristaos"]),
    ("Variedades",    ["variedades", "variedade", "entretenimento", "variety",
                        "geral", "diversos", "diversao"]),
    ("Abertos",       ["abertos", "aberta", "abertas", "tv aberta",
                        "canais abertos", "tvs abertas"]),
    ("24 Horas",      ["24 horas", "24h", "24hs", "24 hrs", "24hrs"]),
    ("Novelas",       ["novelas", "novela", "soap"]),
    ("Culinaria",     ["culinaria", "gastronomia", "comida", "food", "cozinha"]),
    ("Adulto",        ["adulto", "adultos", "+18", "18+", "xxx", "adult"]),
]


def _slug(texto):
    """minuscula, sem acentos, sem pontuacao, espacos colapsados."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[|/\\\-_,.;:]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


# indice sinonimo -> nome canonico
_MAPA_SIN = {}
for _canon, _alts in SINONIMOS:
    for _a in _alts:
        _MAPA_SIN[_slug(_a)] = _canon

# cache para categorias desconhecidas (garante fusao maiusc/minusc estavel)
_CACHE_CAT = {}


def normalizar_categoria(bruta):
    """Retorna o nome final da categoria juntando caixa e sinonimos."""
    s = _slug(bruta)
    if not s:
        return "Outros"
    # 1) match exato de sinonimo
    if s in _MAPA_SIN:
        return _MAPA_SIN[s]
    # 2) match por palavra-chave contida (ex.: "filmes nacionais" -> Filmes)
    for palavra, canon in _MAPA_SIN.items():
        if re.search(r"\b" + re.escape(palavra) + r"\b", s):
            return canon
    # 3) desconhecida: funde apenas por caixa/acentos, mantem titulo apresentavel
    if s not in _CACHE_CAT:
        _CACHE_CAT[s] = " ".join(w.capitalize() for w in s.split())
    return _CACHE_CAT[s]


# --------------------------------------------------------------------------
# HTTP (stdlib)
# --------------------------------------------------------------------------
def _headers(extra=None):
    h = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Origin": BASE_SITE,
        "Referer": BASE_SITE + "/canais",
    }
    tok = os.environ.get("SOPLAY_TOKEN")
    if tok:
        h["Authorization"] = tok if tok.lower().startswith("bearer") else "Bearer " + tok
    if extra:
        h.update(extra)
    return h


def http_get(url, headers=None, raw=False):
    req = request.Request(url, headers=headers or _headers())
    with request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    if raw:
        return data
    return data.decode("utf-8", "replace")


def http_json(url, headers=None):
    txt = http_get(url, headers=headers)
    return json.loads(txt)


def _dump_debug(nome, conteudo):
    if not DEBUG:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    with open(os.path.join(DEBUG_DIR, nome), "w", encoding="utf-8") as f:
        f.write(conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------
# Extracao dos canais da fonte
# --------------------------------------------------------------------------
# Campos possiveis nos JSONs da plataforma (NxPlay/NxTV e similares).
CAMPO_NOME  = ("name", "title", "nome", "channel_name", "titulo")
CAMPO_URL   = ("url", "stream", "stream_url", "streamUrl", "link", "source",
               "src", "hls", "m3u8", "playback_url", "playbackUrl", "file")
CAMPO_GRUPO = ("group", "group_title", "groupTitle", "category", "categoria",
               "genre", "genero", "grupo", "section", "type")
CAMPO_LOGO  = ("logo", "image", "img", "icon", "thumbnail", "thumb", "poster",
               "cover", "logo_url", "tvg_logo", "picture")


def _primeiro(d, chaves):
    for k in chaves:
        if isinstance(d, dict) and d.get(k):
            v = d.get(k)
            if isinstance(v, (str, int, float)):
                return str(v)
    return ""


def _achar_lista_canais(obj):
    """Varre recursivamente um JSON procurando listas de objetos tipo canal."""
    achados = []

    def parece_canal(d):
        return isinstance(d, dict) and _primeiro(d, CAMPO_URL) and _primeiro(d, CAMPO_NOME)

    def walk(o):
        if isinstance(o, list):
            if o and all(parece_canal(x) for x in o if isinstance(x, dict)):
                achados.extend(x for x in o if parece_canal(x))
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)

    walk(obj)
    return achados


def _parse_m3u(texto):
    """Fallback: fonte entregue como M3U (texto)."""
    canais = []
    nome = grupo = logo = ""
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.startswith("#EXTINF"):
            m = re.search(r'group-title="([^"]*)"', linha)
            grupo = m.group(1) if m else ""
            m = re.search(r'tvg-logo="([^"]*)"', linha)
            logo = m.group(1) if m else ""
            nome = linha.split(",", 1)[-1].strip()
        elif linha and not linha.startswith("#"):
            canais.append({"nome": nome, "url": linha, "grupo": grupo, "logo": logo})
            nome = grupo = logo = ""
    return canais


# Endpoints candidatos para descoberta automatica (ajuste SOPLAY_API se mudar).
CANDIDATOS = [
    "https://soplay.com.br/api/channels",
    "https://soplay.com.br/api/canais",
    "https://soplay.com.br/api/v1/channels",
    "https://soplay.com.br/api/live",
    "https://soplay.com.br/api/tv",
]


def coletar_fonte():
    """Retorna lista de dicts {nome,url,grupo,logo}. Levanta excecao se a
    fonte inteira estiver inacessivel (para acionar a protecao anti-queda)."""
    api = os.environ.get("SOPLAY_API")
    urls = ([api] if api else []) + CANDIDATOS
    ult_erro = None
    brutos = []

    for url in urls:
        try:
            dados = http_get(url)
        except Exception as e:  # noqa
            ult_erro = e
            log(f"  [fonte] falhou {url} -> {e}")
            continue
        _dump_debug("fonte_" + _slug(url).replace(" ", "_")[:40] + ".txt", dados)
        # tenta JSON
        try:
            obj = json.loads(dados)
            lista = _achar_lista_canais(obj)
            if lista:
                log(f"  [fonte] {len(lista)} itens via JSON em {url}")
                for it in lista:
                    brutos.append({
                        "nome":  _primeiro(it, CAMPO_NOME).strip(),
                        "url":   _primeiro(it, CAMPO_URL).strip(),
                        "grupo": _primeiro(it, CAMPO_GRUPO).strip(),
                        "logo":  _primeiro(it, CAMPO_LOGO).strip(),
                    })
                break
        except (ValueError, json.JSONDecodeError):
            pass
        # tenta M3U
        if "#EXTINF" in dados:
            lista = _parse_m3u(dados)
            if lista:
                log(f"  [fonte] {len(lista)} itens via M3U em {url}")
                brutos.extend(lista)
                break

    if not brutos:
        raise RuntimeError(
            "Nao foi possivel extrair canais da fonte. "
            "Capture o endpoint real em F12 > Network (XHR/Fetch) e rode com "
            "SOPLAY_API=<url> (e SOPLAY_TOKEN=<token> se precisar). "
            + (f"Ultimo erro: {ult_erro}" if ult_erro else "")
        )
    return brutos


def stream_vivo(url):
    """HEAD/GET rapido para saber se o .m3u8 responde."""
    try:
        req = request.Request(url, headers=_headers({"Range": "bytes=0-1"}))
        with request.urlopen(req, timeout=12) as r:
            return 200 <= r.status < 400
    except error.HTTPError as e:
        return e.code in (200, 206, 301, 302, 403)  # 403 pode ser geo, nao "morto"
    except Exception:
        return False


# --------------------------------------------------------------------------
# Estado (reconciliacao das 3 falhas)
# --------------------------------------------------------------------------
def carregar_estado():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                st = json.load(f)
            st.setdefault("canais", {})
            return st
        except Exception as e:  # noqa
            log(f"  [estado] arquivo corrompido, recomecando ({e})")
    return {"canais": {}, "atualizado_em": ""}


def salvar_estado(st):
    st["atualizado_em"] = dt.datetime.now().isoformat(timespec="seconds")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Escrita da playlist M3U (SS IPTV)
# --------------------------------------------------------------------------
def escrever_m3u(canais):
    """canais: lista de dicts {nome,url,grupo,logo} ja normalizados."""
    os.makedirs(OUT_DIR, exist_ok=True)
    # agrupa por categoria e ordena categorias e canais
    por_cat = {}
    for c in canais:
        por_cat.setdefault(c["grupo"], []).append(c)
    linhas = ["#EXTM3U"]
    for cat in sorted(por_cat, key=lambda x: _slug(x)):
        for c in sorted(por_cat[cat], key=lambda x: _slug(x["nome"])):
            logo = f' tvg-logo="{c["logo"]}"' if c.get("logo") else ""
            linhas.append(
                f'#EXTINF:-1 tvg-name="{c["nome"]}"{logo} '
                f'group-title="{cat}",{c["nome"]}'
            )
            linhas.append(c["url"])
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    return por_cat


# --------------------------------------------------------------------------
# Fluxo principal
# --------------------------------------------------------------------------
def main():
    inicio = time.time()
    log("=" * 64)
    log("Gerador M3U SO Play -> SS IPTV")
    log(f"Inicio: {dt.datetime.now().isoformat(timespec='seconds')}")
    log(f"Checar liveness (SOPLAY_CHECK): {'sim' if CHECK else 'nao'}")
    log("=" * 64)

    estado = carregar_estado()
    canais_estado = estado["canais"]

    # 1) coleta da fonte (com protecao anti-queda geral)
    try:
        brutos = coletar_fonte()
    except Exception as e:  # noqa
        log(f"\n[AVISO] Fonte inacessivel: {e}")
        log("[AVISO] Mantendo estado e playlist anteriores (sem penalizar canais).")
        # regenera a playlist com o que ja esta ativo no estado
        ativos = [c for c in canais_estado.values() if c.get("falhas", 0) < MAX_FALHAS]
        if ativos:
            escrever_m3u(ativos)
            log(f"[AVISO] Playlist preservada com {len(ativos)} canais.")
        salvar_estado(estado)
        return 0

    log(f"\nCanais brutos vistos na fonte: {len(brutos)}")

    # 2) dedup por URL + normalizacao de categoria
    vistos_url = set()
    atuais = {}
    dups = 0
    for b in brutos:
        url = (b.get("url") or "").strip()
        nome = (b.get("nome") or "").strip() or "Sem nome"
        if not url:
            continue
        if url in vistos_url:
            dups += 1
            continue
        vistos_url.add(url)
        atuais[url] = {
            "nome":  nome,
            "url":   url,
            "grupo": normalizar_categoria(b.get("grupo")),
            "logo":  (b.get("logo") or "").strip(),
        }
    log(f"Canais unicos apos remover links duplicados: {len(atuais)} ({dups} duplicados descartados)")

    # 3) liveness opcional
    funcionando = dict(atuais)
    if CHECK and atuais:
        log("\nTestando liveness dos streams...")
        mortos = []
        with ThreadPoolExecutor(max_workers=16) as ex:
            fut = {ex.submit(stream_vivo, u): u for u in atuais}
            for f in as_completed(fut):
                u = fut[f]
                if not f.result():
                    mortos.append(u)
        for u in mortos:
            funcionando.pop(u, None)
        log(f"Streams respondendo: {len(funcionando)} | sem resposta agora: {len(mortos)}")

    # 4) reconciliacao com a regra das 3 falhas
    novos = reativados = 0
    for url, c in atuais.items():
        if url in funcionando:
            if url not in canais_estado:
                novos += 1
            elif canais_estado[url].get("falhas", 0) > 0:
                reativados += 1
            canais_estado[url] = {
                **c,
                "falhas": 0,
                "visto_em": dt.datetime.now().isoformat(timespec="seconds"),
            }
        else:
            # apareceu na fonte mas nao respondeu -> conta como 1 falha
            prev = canais_estado.get(url, {**c, "falhas": 0})
            prev.update({k: c[k] for k in ("nome", "grupo", "logo")})
            prev["falhas"] = prev.get("falhas", 0) + 1
            canais_estado[url] = prev

    # canais que estavam no estado mas sumiram da fonte agora -> +1 falha
    sumiram = [u for u in list(canais_estado) if u not in atuais]
    for u in sumiram:
        canais_estado[u]["falhas"] = canais_estado[u].get("falhas", 0) + 1

    # remove quem falhou MAX_FALHAS vezes seguidas
    removidos = [u for u, c in canais_estado.items() if c.get("falhas", 0) >= MAX_FALHAS]
    for u in removidos:
        canais_estado.pop(u, None)

    # 5) monta playlist com todos os ativos (falhas < 3)
    ativos = [c for c in canais_estado.values() if c.get("falhas", 0) < MAX_FALHAS]
    por_cat = escrever_m3u(ativos)
    salvar_estado(estado)

    # 6) resumo
    log("\n" + "-" * 64)
    log(f"Novos canais:           {novos}")
    log(f"Reativados (zeraram falha): {reativados}")
    log(f"Sumiram/falharam agora: {len(sumiram) + (len(atuais) - len(funcionando))}")
    log(f"Removidos (3 falhas):   {len(removidos)}")
    log(f"Total ATIVO na lista:   {len(ativos)}")
    log(f"Categorias ({len(por_cat)}):")
    for cat in sorted(por_cat, key=lambda x: _slug(x)):
        log(f"   - {cat}: {len(por_cat[cat])}")
    log(f"\nArquivo gerado: {OUT_FILE}")
    log(f"Tempo total: {time.time() - inicio:.1f}s")
    log("=" * 64)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
