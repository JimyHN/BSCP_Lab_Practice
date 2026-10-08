#!/usr/bin/env python3
"""Elige laboratorios aleatorios de la PortSwigger Web Security Academy.

Abre la pagina de descripcion de cada lab (la del boton "Access the lab").
No lanza la instancia del lab: ese click lo das tu.
"""

import argparse
import json
import os
import random
import re
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ALL_LABS = "https://portswigger.net/web-security/all-labs"
WIDGETS_API = "https://portswigger.net/api/widgets"
BASE = "https://portswigger.net"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"

HERE = Path(__file__).resolve().parent
CACHE = HERE / "labs.json"
HISTORY = HERE / "history.json"
GROUPS_CFG = HERE / "groups.json"

DIFFICULTIES = ("apprentice", "practitioner", "expert")

# ---------------------------------------------------------------- color -----
# Nunca se usa blanco ni el color por defecto del terminal: todo va teñido.
USE_COLOR = os.environ.get("NO_COLOR") is None

_C = {
    "head": "\033[1;36m",     # cian brillante  - titulos de seccion
    "sep": "\033[38;5;240m",  # gris            - separadores
    "ok": "\033[1;32m",       # verde           - permitidos / exito
    "bad": "\033[1;31m",      # rojo            - no permitidos / errores
    "warn": "\033[1;33m",     # amarillo        - avisos y prompts
    "title": "\033[1;35m",    # magenta         - titulo del lab
    "url": "\033[4;94m",      # azul subrayado  - urls
    "num": "\033[1;36m",      # cian            - indices de menu
    "info": "\033[36m",       # cian apagado    - texto informativo
    "group": "\033[38;5;214m",  # naranja       - nombre de grupo
    "R": "\033[0m",
}

DIFF_COLOR = {"apprentice": "ok", "practitioner": "warn", "expert": "bad"}


def c(style, text):
    """Tiñe texto. Si el color esta desactivado devuelve el texto tal cual."""
    if not USE_COLOR:
        return str(text)
    return f"{_C[style]}{text}{_C['R']}"


def p(style, text=""):
    print(c(style, text))


def err(text):
    print(c("bad", text), file=sys.stderr)


def rule(style="sep", width=56, ch="_"):
    p(style, ch * width)


# ------------------------------------------------------------- descarga -----
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _post_widgets(lab_ids):
    """Resuelve ids de lab a titulo/dificultad/url con el endpoint de la propia web."""
    payload = [
        {"widgetId": "academy-labstatus", "additionalData": {"widget-lab-id": i}}
        for i in lab_ids
    ]
    req = urllib.request.Request(
        WIDGETS_API,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Widget-Source": "/web-security/all-labs",
            "User-Agent": UA,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_labs():
    """Descarga la lista completa de labs: grupo, dificultad, titulo y url."""
    html = _get(ALL_LABS)

    # Recorremos el HTML en orden para asociar cada lab-id con su <h2> de grupo.
    group_of, current = {}, "unknown"
    pattern = re.compile(
        r'<h2[^>]*id="(?P<gid>[^"]+)"[^>]*>(?P<gtext>.*?)</h2>'
        r'|widget-lab-id="(?P<lab>[0-9A-Fa-f]{32,})"',
        re.S,
    )
    for m in pattern.finditer(html):
        if m.group("lab"):
            group_of[m.group("lab")] = current
        else:
            current = re.sub(r"<[^>]+>", "", m.group("gtext")).strip()

    ids = list(group_of)
    if not ids:
        err("No se encontro ningun lab en all-labs; la pagina pudo cambiar.")
        sys.exit(1)

    link_re = re.compile(r'<a href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
    diff_re = re.compile(r'label-[a-z-]*small">\s*(?P<diff>[A-Z]+)\s*<')

    labs, order = [], {lab_id: n for n, lab_id in enumerate(ids)}
    for start in range(0, len(ids), 50):
        chunk = ids[start : start + 50]
        for lab_id, widget in zip(chunk, _post_widgets(chunk)):
            frag = widget.get("Html", "")
            link = link_re.search(frag)
            if not link:
                continue
            diff = diff_re.search(frag)
            labs.append(
                {
                    "id": lab_id,
                    "title": re.sub(r"\s+", " ", link.group("title")).strip(),
                    "url": BASE + link.group("url"),
                    "group": group_of[lab_id],
                    "difficulty": diff.group("diff").lower() if diff else "unknown",
                }
            )
        p("info", f"  resueltos {min(start + 50, len(ids))}/{len(ids)}")

    labs.sort(key=lambda l: order[l["id"]])
    return labs


# ------------------------------------------------------------- estado -------
def load_labs(update=False):
    if update or not CACHE.exists():
        p("head", "Descargando lista de labs de PortSwigger...")
        try:
            labs = fetch_labs()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            err(f"Fallo la descarga: {e}")
            if CACHE.exists():
                p("warn", "Sigo con la cache existente.")
                return json.loads(CACHE.read_text(encoding="utf-8"))
            sys.exit(1)
        CACHE.write_text(json.dumps(labs, indent=1, ensure_ascii=False), encoding="utf-8")
        p("ok", f"Guardados {len(labs)} labs en {CACHE.name}")
        return labs

    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        err(f"{CACHE.name} ilegible. Ejecuta: randomlab.py --update")
        sys.exit(1)


def _read_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def load_history():
    data = _read_json(HISTORY, [])
    return data if isinstance(data, list) else []


def save_history(ids):
    HISTORY.write_text(json.dumps(ids, indent=1), encoding="utf-8")


def all_groups(labs):
    """Grupos en el orden en que aparecen en all-labs."""
    seen = []
    for lab in labs:
        if lab["group"] not in seen:
            seen.append(lab["group"])
    return seen


def load_allowed(labs):
    """Grupos permitidos. Por defecto ninguno: todos arrancan en no permitidos."""
    data = _read_json(GROUPS_CFG, {})
    allowed = data.get("allowed", []) if isinstance(data, dict) else []
    valid = set(all_groups(labs))
    return [g for g in allowed if g in valid]


def save_allowed(allowed):
    GROUPS_CFG.write_text(
        json.dumps({"allowed": allowed}, indent=1, ensure_ascii=False), encoding="utf-8"
    )


# -------------------------------------------------------------- login -------
LOGIN_URL = "https://portswigger.net/users/login"
SESSION_CFG = HERE / "session.json"

# El login de PortSwigger es OIDC (login.portswigger.net, OAuth2 + PKCE): la sesion
# vive en las cookies del navegador, no aqui. Para saber si estas logueado miramos
# la cookie de sesion en el perfil de Firefox.
#
# NUNCA se lee la columna 'value' de la base de cookies: solo el nombre y la
# caducidad. El token de sesion no se lee, ni se guarda, ni se imprime.
FIREFOX_COOKIE_GLOBS = (
    "~/snap/firefox/common/.mozilla/firefox/*/cookies.sqlite",
    "~/.mozilla/firefox/*/cookies.sqlite",
    "~/.var/app/org.mozilla.firefox/.mozilla/firefox/*/cookies.sqlite",
)

# Cookies que indican sesion iniciada (portswigger.net corre ASP.NET Core + OIDC).
AUTH_COOKIE_RE = re.compile(
    r"^\.AspNetCore\.(Cookies|Identity\.Application)$"
    r"|^\.AspNet\.ApplicationCookie$"
    r"|^__Secure-.*(auth|session)"
    r"|^PortSwigger.*(Auth|Session|Identity)"
    r"|(Auth|Session)Id$",
    re.I,
)
# Ruido que tiene cualquier visitante anonimo: no cuenta como login.
NOISE_COOKIE_RE = re.compile(
    r"consent|^_ga|^_gid|^_gcl|^_fbp|hubspot|^__cf|^__hs|utm|optimizely|^ai_|^ARRAffinity",
    re.I,
)
SESSION_TTL_DAYS = 14


def find_cookie_db():
    """Devuelve el cookies.sqlite mas reciente de los perfiles de Firefox."""
    import glob

    found = [
        Path(hit)
        for pattern in FIREFOX_COOKIE_GLOBS
        for hit in glob.glob(os.path.expanduser(pattern))
        if Path(hit).is_file()
    ]
    if not found:
        return None
    return max(found, key=lambda f: f.stat().st_mtime)


def portswigger_cookie_names(db=None):
    """Nombres y caducidad de las cookies de portswigger.net. Nunca sus valores.

    Devuelve (lista de (nombre, expiry), error) y la lista va vacia si no hay nada.
    """
    import shutil
    import sqlite3
    import tempfile

    db = db or find_cookie_db()
    if db is None:
        return [], "no encontre ningun perfil de Firefox"

    # Firefox mantiene la base abierta: trabajamos sobre una copia (con su -wal).
    tmpdir = tempfile.mkdtemp(prefix="randomlab-ck-")
    try:
        copy = Path(tmpdir) / "cookies.sqlite"
        shutil.copy2(db, copy)
        for suffix in ("-wal", "-shm"):
            side = Path(str(db) + suffix)
            if side.exists():
                shutil.copy2(side, str(copy) + suffix)
        try:
            con = sqlite3.connect(str(copy))
            rows = con.execute(
                "SELECT name, expiry FROM moz_cookies "
                "WHERE host LIKE '%portswigger.net'"
            ).fetchall()
            con.close()
        except sqlite3.Error as e:
            return [], f"no pude leer la base de cookies ({e})"
        return rows, None
    except OSError as e:
        return [], f"no pude copiar la base de cookies ({e})"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def detect_login(db=None):
    """(logueado, nombre_de_cookie, nota). Solo mira nombres y caducidades."""
    import time

    rows, problem = portswigger_cookie_names(db)
    if problem:
        return None, None, problem

    now = time.time()
    for name, expiry in rows:
        if NOISE_COOKIE_RE.search(name or ""):
            continue
        if not AUTH_COOKIE_RE.search(name or ""):
            continue
        # expiry 0 = cookie de sesion, viva mientras el navegador siga abierto.
        if not expiry or expiry > now:
            return True, name, None
    if rows:
        return False, None, f"{len(rows)} cookies de portswigger.net, ninguna de sesion"
    return False, None, "sin cookies de portswigger.net en el perfil"


def marker_ok():
    """Respaldo si no se puede inspeccionar el navegador: marca de --login."""
    import time

    data = _read_json(SESSION_CFG, {})
    if not isinstance(data, dict) or not data.get("logged_in"):
        return False
    return (time.time() - data.get("at", 0)) / 86400 < SESSION_TTL_DAYS


def mark_logged_in():
    import time

    SESSION_CFG.write_text(
        json.dumps({"logged_in": True, "at": time.time()}, indent=1), encoding="utf-8"
    )


def login_state_ok():
    """True si Firefox tiene sesion de PortSwigger. Si no se puede comprobar,
    cae en la marca local de --login para no bloquear el programa."""
    ok, _name, problem = detect_login()
    if ok is None:
        return marker_ok()
    return ok or marker_ok()


def do_login():
    """Abre el navegador en el login de PortSwigger y comprueba el resultado."""
    p("head", "\nLOGIN EN PORTSWIGGER")
    rule()
    ok, name, problem = detect_login()
    if ok:
        p("ok", f"  Ya estas logueado (cookie {name}).")
        p("info", "  Si quieres cambiar de cuenta, entra de nuevo en:")
        p("url", f"  {LOGIN_URL}\n")
        mark_logged_in()
        return

    p("info", "  Te abro el navegador en el login. Entra con tu cuenta ahi:")
    p("url", f"  {LOGIN_URL}")
    p("info", "  La sesion queda en Firefox, asi que los labs que abra este")
    p("info", "  script se abriran ya con tu cuenta.")
    if problem:
        p("sep", f"  ({problem})")
    print()
    if not open_in_browser(LOGIN_URL):
        err("  No pude lanzar el navegador. Abre la URL de arriba a mano.")
    ask("  Pulsa Enter cuando hayas terminado el login: ")

    ok, name, problem = detect_login()
    if ok:
        mark_logged_in()
        p("ok", f"\n  Login confirmado en Firefox (cookie {name}). Listo.\n")
        return
    if ok is None:
        p("warn", f"\n  No puedo inspeccionar Firefox: {problem}")
        answer = ask("  Has completado el login? [s/N]: ").lower()
        if answer in ("s", "si", "sí", "y", "yes"):
            mark_logged_in()
            p("ok", "\n  Apuntado. Ya puedes pedir labs.\n")
        else:
            p("warn", "\n  No he apuntado nada. Vuelve a lanzar --login.\n")
        return
    p("bad", "\n  Sigo sin ver sesion de PortSwigger en Firefox.")
    if problem:
        p("sep", f"  ({problem})")
    p("info", "  Si de verdad entraste, mira los nombres de cookie con:")
    p("num", "      randomlab.py --login --debug-cookies\n")


def debug_cookies():
    """Lista los NOMBRES de cookie de portswigger.net. Nunca sus valores."""
    import time

    p("head", "\nCOOKIES DE PORTSWIGGER.NET EN TU PERFIL DE FIREFOX")
    rule()
    db = find_cookie_db()
    p("info", f"  perfil: {db if db else 'no encontrado'}")
    rows, problem = portswigger_cookie_names(db)
    if problem:
        err(f"  {problem}")
        print()
        return
    if not rows:
        p("warn", "  Ninguna cookie de portswigger.net.")
        print()
        return
    now = time.time()
    for name, expiry in sorted(rows):
        if NOISE_COOKIE_RE.search(name or ""):
            tag, style = "ruido", "sep"
        elif AUTH_COOKIE_RE.search(name or ""):
            tag, style = ("sesion" if (not expiry or expiry > now) else "caducada"), (
                "ok" if (not expiry or expiry > now) else "bad"
            )
        else:
            tag, style = "otra", "info"
        print(f"  {c(style, f'{tag:9}')} {c('group', name)}")
    p("sep", "\n  Solo se leen nombres y caducidades, nunca el valor de la cookie.")
    p("info", "  Si la cookie de tu sesion sale como 'otra', dime su nombre y la")
    p("info", "  anado a AUTH_COOKIE_RE.\n")


def require_login():
    """Corta el programa si no hay sesion de PortSwigger."""
    if login_state_ok():
        return
    ok, _name, problem = detect_login()
    print()
    p("bad", "No estas logueado en PortSwigger.")
    if problem:
        p("sep", f"  ({problem})")
    p("warn", "Los labs necesitan tu cuenta para poder iniciarse.")
    p("info", "Lanza primero:")
    p("num", "    randomlab.py --login")
    print()
    sys.exit(2)


# ------------------------------------------------------------- consola ------
def ask(prompt):
    """input() teñido. Ctrl+C o EOF cierran el programa como pide 'Salir'."""
    try:
        return input(c("warn", prompt)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        p("warn", "Saliendo.")
        sys.exit(130)


def open_in_browser(url):
    try:
        subprocess.Popen(
            ["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except (OSError, ValueError):
        return False


def parse_selection(raw, total):
    """'1,4,5' -> [0,3,4]. 'exit' si es 0. None si hay algo invalido."""
    if raw.strip() == "0":
        return "exit"
    picks = []
    for tok in re.split(r"[,\s]+", raw.strip()):
        if not tok:
            continue
        if not tok.isdigit() or not 1 <= int(tok) <= total:
            return None
        if int(tok) - 1 not in picks:
            picks.append(int(tok) - 1)
    return picks or None


# --------------------------------------------------- menu --limit-group -----
def show_group_lists(allowed, not_allowed, counts):
    print()
    p("head", "GRUPOS PERMITIDOS")
    rule()
    if allowed:
        for g in allowed:
            print(f"  {c('ok', '+')} {c('group', g)} {c('info', f'({counts[g]} labs)')}")
    else:
        p("warn", "  (ninguno: sin restriccion, entran todos los grupos)")
    print()
    p("head", "GRUPOS NO PERMITIDOS")
    rule()
    if not_allowed:
        for g in not_allowed:
            print(f"  {c('bad', '-')} {c('group', g)} {c('info', f'({counts[g]} labs)')}")
    else:
        p("ok", "  (ninguno)")
    print()


def choose_groups(pool, counts, title, verb):
    """Muestra 'pool' numerado y devuelve los grupos elegidos."""
    if not pool:
        p("warn", f"\n  No hay grupos que {verb}.\n")
        return []
    print()
    p("head", title)
    rule()
    for n, g in enumerate(pool, 1):
        print(f"  {c('num', f'{n:2}.')} {c('group', g)} {c('info', f'({counts[g]} labs)')}")
    print(f"  {c('num', ' 0.')} {c('info', 'Volver al menu')}")
    print()
    while True:
        raw = ask("  Numeros separados por comas (ej. 1,4,5): ")
        sel = parse_selection(raw, len(pool))
        if sel == "exit":
            return []
        if sel is None:
            err(f"  Entrada no valida. Usa numeros del 1 al {len(pool)}, o 0 para volver.")
            continue
        return [pool[i] for i in sel]


def limit_group_menu(labs):
    """Menu interactivo para mover grupos entre permitidos y no permitidos."""
    from collections import Counter

    counts = Counter(l["group"] for l in labs)
    order = all_groups(labs)
    allowed = load_allowed(labs)

    while True:
        not_allowed = [g for g in order if g not in allowed]
        show_group_lists([g for g in order if g in allowed], not_allowed, counts)

        p("head", "QUE QUIERES HACER")
        rule()
        print(f"  {c('num', '1.')} {c('info', 'Anadir a permitidos')}")
        print(f"  {c('num', '2.')} {c('info', 'Eliminar de permitidos')}")
        print(f"  {c('num', '0.')} {c('info', 'Salir')}")
        print()
        opt = ask("  Opcion: ")

        if opt == "0":
            p("warn", "\n  Saliendo.\n")
            return
        if opt == "1":
            picked = choose_groups(not_allowed, counts, "GRUPOS NO PERMITIDOS", "anadir")
            for g in picked:
                if g not in allowed:
                    allowed.append(g)
            if picked:
                save_allowed([g for g in order if g in allowed])
                p("ok", f"\n  Movidos a permitidos: {len(picked)}")
        elif opt == "2":
            current = [g for g in order if g in allowed]
            picked = choose_groups(current, counts, "GRUPOS PERMITIDOS", "eliminar")
            allowed = [g for g in allowed if g not in picked]
            if picked:
                save_allowed([g for g in order if g in allowed])
                p("ok", f"\n  Movidos a no permitidos: {len(picked)}")
        else:
            err("  Opcion no valida. Elige 1, 2 o 0.")


# --------------------------------------------------------- seleccion --------
def distribute(count, by_group):
    """Reparte 'count' labs entre los grupos: nunca dos del mismo grupo hasta
    que todos tengan uno, y el resto se reparte de uno en uno."""
    groups = [g for g, labs in by_group.items() if labs]
    if not groups:
        return []
    random.shuffle(groups)
    n_groups = len(groups)

    if count <= n_groups:
        quota = {g: 1 for g in groups[:count]}
    else:
        base, rem = divmod(count, n_groups)
        quota = {g: base for g in groups}
        for g in groups[:rem]:
            quota[g] += 1

    # Si un grupo no tiene labs suficientes, el excedente va a los que si.
    overflow = 0
    for g in list(quota):
        avail = len(by_group[g])
        if quota[g] > avail:
            overflow += quota[g] - avail
            quota[g] = avail
    while overflow > 0:
        moved = False
        for g in groups:
            if overflow <= 0:
                break
            if quota.get(g, 0) < len(by_group[g]):
                quota[g] = quota.get(g, 0) + 1
                overflow -= 1
                moved = True
        if not moved:
            break

    picked = {g: random.sample(by_group[g], q) for g, q in quota.items() if q}
    # Entrelazamos para que dos consecutivos no sean del mismo grupo.
    out = []
    while any(picked.values()):
        for g in groups:
            if picked.get(g):
                out.append(picked[g].pop())
    return out


def matches_filters(lab, topic, difficulty):
    if difficulty and lab["difficulty"] not in difficulty:
        return False
    if topic:
        hay = f"{lab['group']} {lab['url']}".lower()
        return any(t.lower() in hay for t in topic)
    return True


def print_lab(lab, index=None, total=None):
    head = f"  {c('num', f'[{index}/{total}]')} " if index else "  "
    print()
    print(head + c("title", lab["title"]))
    diff = lab["difficulty"]
    print(
        f"  {c(DIFF_COLOR.get(diff, 'info'), diff.upper())}"
        f" {c('sep', '|')} {c('group', lab['group'])}"
    )
    print(f"  {c('url', lab['url'])}")


# ---------------------------------------------------------------- cli -------
def _colorize_help(text):
    """Tiñe la ayuda de argparse: ni una linea en blanco por defecto."""
    if not USE_COLOR:
        return text
    out = []
    for line in text.splitlines():
        if re.match(r"^\S.*:$", line):
            out.append(c("head", line))
            continue
        line = re.sub(
            r"(--?[A-Za-z][\w-]*)",
            lambda m: _C["num"] + m.group(1) + _C["R"] + _C["info"],
            line,
        )
        out.append(_C["info"] + line + _C["R"])
    return "\n".join(out) + "\n"


class ColorParser(argparse.ArgumentParser):
    def format_help(self):
        return _colorize_help(super().format_help())

    def format_usage(self):
        return _colorize_help(super().format_usage())

    def error(self, message):
        self.print_usage()
        err(f"error: {message}")
        sys.exit(2)


def build_parser():
    ap = ColorParser(
        prog="randomlab.py",
        description="Elige labs aleatorios de la PortSwigger Web Security Academy y abre "
        "su pagina de descripcion (la del boton 'Access the lab').",
        epilog="Ejemplos:\n"
        "  randomlab.py                 un lab aleatorio\n"
        "  randomlab.py 3               tres labs, cada uno de un grupo distinto\n"
        "  randomlab.py --limit-group   gestiona que grupos entran en el sorteo\n"
        "  randomlab.py --login         entra con tu cuenta en el navegador\n"
        "  randomlab.py 5 --no-open     cinco labs, solo listados\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "count", nargs="?", type=int, default=1,
        help="cuantos labs abrir (por defecto 1). Nunca repite grupo hasta "
             "haber usado todos los permitidos",
    )
    ap.add_argument("--login", action="store_true",
                    help="abre el navegador para que entres con tu cuenta de PortSwigger")
    ap.add_argument("--debug-cookies", action="store_true",
                    help="lista los NOMBRES de cookie de portswigger.net de tu perfil "
                         "de Firefox (nunca sus valores) para afinar la deteccion")
    ap.add_argument("--limit-group", action="store_true",
                    help="menu para mover grupos entre permitidos y no permitidos")
    ap.add_argument("-g", "--groups", action="store_true",
                    help="lista los grupos con su estado y su numero de labs")
    ap.add_argument("-t", "--topic", action="append", metavar="TEXTO",
                    help="filtro extra por subcadena de grupo o url (repetible)")
    ap.add_argument("-d", "--difficulty", action="append", choices=DIFFICULTIES,
                    help="filtra por dificultad (repetible)")
    ap.add_argument("-l", "--list", action="store_true",
                    help="lista los labs que cuadran con el filtro y sale")
    ap.add_argument("--no-open", action="store_true",
                    help="no abre el navegador, solo imprime")
    ap.add_argument("--repeat", action="store_true",
                    help="permite volver a sacar labs ya vistos")
    ap.add_argument("--reset", action="store_true",
                    help="vacia el historial de labs ya vistos")
    ap.add_argument("--update", action="store_true",
                    help="refresca labs.json desde portswigger.net")
    ap.add_argument("--no-color", action="store_true",
                    help="desactiva el color (tambien sirve NO_COLOR=1)")
    return ap


def cmd_groups(labs, allowed):
    from collections import Counter

    counts = Counter(l["group"] for l in labs)
    order = all_groups(labs)
    show_group_lists([g for g in order if g in allowed],
                     [g for g in order if g not in allowed], counts)
    p("info", f"  {len(order)} grupos, {len(labs)} labs en total.")
    p("sep", "  Usa --limit-group para mover grupos entre las dos listas.")
    print()


def run(args):
    if args.count < 1:
        err("El numero de labs tiene que ser 1 o mas.")
        sys.exit(2)

    if args.debug_cookies:
        debug_cookies()
        return

    if args.login:
        do_login()
        return

    labs = load_labs(update=args.update)

    if args.limit_group:
        limit_group_menu(labs)
        return

    allowed = load_allowed(labs)

    if args.groups:
        cmd_groups(labs, allowed)
        return

    if args.reset:
        HISTORY.unlink(missing_ok=True)
        p("ok", "Historial vaciado.")
        if args.update:
            return

    # Sin grupos permitidos no habria nada que sortear: entran todos.
    if allowed:
        pool = [l for l in labs if l["group"] in allowed]
    else:
        p("warn", "Sin grupos permitidos todavia: sorteo entre todos "
                  "(usa --limit-group para restringir).")
        pool = list(labs)

    pool = [l for l in pool if matches_filters(l, args.topic, args.difficulty)]
    if not pool:
        err("Ningun lab cuadra con el filtro. Prueba --groups para ver que hay.")
        sys.exit(1)

    if args.list:
        for lab in pool:
            print_lab(lab)
        print()
        p("info", f"  {len(pool)} labs.")
        print()
        return

    if not args.no_open:
        require_login()

    history = load_history()
    if not args.repeat:
        fresh = [l for l in pool if l["id"] not in history]
        if fresh:
            pool = fresh
        else:
            p("warn", "Ya has visto todos los labs de este filtro: reinicio la ronda.")
            history = [i for i in history if i not in {l["id"] for l in pool}]

    by_group = {}
    for lab in pool:
        by_group.setdefault(lab["group"], []).append(lab)

    picks = distribute(args.count, by_group)
    if len(picks) < args.count:
        p("warn", f"Solo quedan {len(picks)} labs disponibles con este filtro.")

    for n, lab in enumerate(picks, 1):
        print_lab(lab, n, len(picks))
        if not args.no_open and not open_in_browser(lab["url"]):
            err("  No pude lanzar el navegador; abre la url a mano.")
        if lab["id"] not in history:
            history.append(lab["id"])
    print()
    save_history(history)


def main():
    global USE_COLOR
    # Permite 'randomlab.py --list | head' sin reventar con BrokenPipeError.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    args = build_parser().parse_args()
    if args.no_color:
        USE_COLOR = False
    try:
        run(args)
    except KeyboardInterrupt:
        print()
        p("warn", "Interrumpido.")
        sys.exit(130)


if __name__ == "__main__":
    main()
