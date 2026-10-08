# RandomLab — labs aleatorios de la PortSwigger Web Security Academy

Elige labs al azar de los 273 de [all-labs](https://portswigger.net/web-security/all-labs)
y abre su **página de descripción** (la del botón *Access the lab*). No lanza la
instancia del lab: ese click lo das tú.

Todo lo que imprime va coloreado. Solo biblioteca estándar de Python 3.

## Uso

```bash
./randomlab.py            # 1 lab aleatorio
./randomlab.py 3          # 3 labs, cada uno de un grupo distinto
./randomlab.py --login    # entrar con tu cuenta en el navegador
./randomlab.py -h         # ayuda completa
```

| Flag | Qué hace |
|---|---|
| `count` (posicional) | cuántos labs abrir, por defecto 1 |
| `--login` | abre el navegador en el login de PortSwigger y comprueba la sesión |
| `--debug-cookies` | lista los *nombres* de cookie de portswigger.net de tu perfil |
| `--limit-group` | menú para elegir qué grupos entran en el sorteo |
| `-g`, `--groups` | lista los grupos con su estado y nº de labs |
| `-t`, `--topic` | filtro extra por subcadena (repetible) |
| `-d`, `--difficulty` | `apprentice` / `practitioner` / `expert` (repetible) |
| `-l`, `--list` | lista lo que cuadra con el filtro y sale |
| `--no-open` | no abre navegador, solo imprime |
| `--repeat` | permite repetir labs ya vistos |
| `--reset` | vacía el historial |
| `--update` | refresca `labs.json` desde portswigger.net |
| `--no-color` | desactiva el color (también `NO_COLOR=1`) |

`Ctrl+C` corta en cualquier momento, igual que la opción `0. Salir` del menú.

## Login

Los labs necesitan tu cuenta. Si pides un lab sin sesión, el programa **corta** y te
manda a `--login`, que te abre el navegador en el login de PortSwigger. La sesión
queda en Firefox, así que los labs se abren ya con tu cuenta.

```bash
./randomlab.py --login
```

La detección es real: se busca el `cookies.sqlite` de tu perfil de Firefox (snap,
nativo o flatpak) y se comprueba si hay una cookie de sesión de `portswigger.net`
viva. Como Firefox mantiene la base abierta, se trabaja sobre una copia junto con su
`-wal`, así que detecta logins recién hechos.

**La consulta SQL es `SELECT name, expiry`: nunca se lee la columna `value`.** El
token de sesión no se lee, ni se guarda, ni se imprime en ningún momento.

Si tu cookie de sesión no se reconoce, mira cómo se clasifica:

```bash
./randomlab.py --debug-cookies
```

Lista los nombres (nunca los valores) marcados como `sesion`, `caducada`, `otra` o
`ruido`. Si la tuya sale como `otra`, añádela a `AUTH_COOKIE_RE` en el script.

Si no se encuentra ningún perfil de Firefox, el programa no se bloquea: `--login` te
pregunta y guarda una marca en `session.json`, válida 14 días.

## Grupos

Los 31 grupos son los temas de `all-labs`: SQL injection, Cross-site scripting,
Clickjacking, CSRF, JWT, Race conditions… `--limit-group` abre este menú:

```
GRUPOS PERMITIDOS
________________________________________________________
  + JWT (8 labs)

GRUPOS NO PERMITIDOS
________________________________________________________
  - SQL injection (18 labs)
  - Cross-site scripting (30 labs)
  ...

QUE QUIERES HACER
________________________________________________________
  1. Anadir a permitidos
  2. Eliminar de permitidos
  0. Salir
```

Eliges `1` o `2`, te sale la lista correspondiente numerada, y marcas uno o varios
con comas (`1,4,5`). En el submenú `0` vuelve al menú principal.

**De partida todos los grupos están en no permitidos.** Mientras la lista de
permitidos esté vacía no hay restricción y el sorteo usa los 31 grupos; en cuanto
metes uno, solo se sortea entre los permitidos. Se guarda en `groups.json`.

## Reparto entre grupos

Pidiendo varios labs nunca te salen dos del mismo grupo hasta que todos los
permitidos tengan uno; lo que sobra se reparte de uno en uno:

| Pides | Grupos permitidos | Reparto |
|---|---|---|
| 2 | 5 | 1+1, de dos grupos al azar |
| 3 | 2 | 2+1 |
| 7 | 3 | 3+2+2 |

Si un grupo se queda sin labs disponibles, su cuota pasa a los que aún tengan.

## Historial

Por defecto no repite un lab ya visto; al agotar el conjunto del filtro reinicia
la ronda. Vive en `history.json` (`--repeat` lo ignora, `--reset` lo vacía).

## Ficheros

- `randomlab.py` — el programa.
- `labs.json` — caché: id, título, url, grupo, dificultad.
- `groups.json` — grupos permitidos.
- `history.json` — labs ya vistos.
- `session.json` — marca de login confirmado.

## Cómo obtiene los labs

`all-labs` no trae los títulos en el HTML: solo `<div widget-id="academy-labstatus"
widget-lab-id="...">`, que la propia web resuelve con un `POST /api/widgets`.
`--update` hace esa misma llamada en lotes de 50 y asocia cada lab al `<h2>` del
grupo que lo precede. Si PortSwigger cambia ese endpoint, `--update` fallará y
habrá que ajustar `fetch_labs()`; mientras, `labs.json` sigue sirviendo.

## Atajo

```bash
echo "alias randomlab='$HOME/Documentos/BurpSuite_RandomLab/randomlab.py'" >> ~/.zshrc
```
