#!/usr/bin/env bash
# =============================================================================
# start_db.sh — Levanta PostgreSQL para FreshTrack.
#
#   ./scripts/start_db.sh          Arranca el servidor
#   ./scripts/start_db.sh status   Comprueba si responde (no arranca nada)
#   ./scripts/start_db.sh stop     Detiene el servidor
#   ./scripts/start_db.sh restart  Reinicia
#
# El puerto se lee de DATABASE_URL en el .env, no se adivina: asi el servidor y
# la aplicacion no pueden discrepar. Si no hay .env, usa POSTGRES_PORT o 5432.
#
# Ubicacion del PostgreSQL portable. Se puede sobreescribir por entorno:
#   PG_HOME   directorio que contiene pgsql/bin y data/   (por defecto ~/.workbuddy-ai/binaries/postgres)
#   PG_DATA   directorio de datos                          (por defecto $PG_HOME/data)
#   PG_LOG    archivo de log                               (por defecto $PG_HOME/server.log)
#
# Si no existe el PostgreSQL portable, el script usa el pg_ctl del PATH (una
# instalacion normal de PostgreSQL). En ese caso hay que definir PG_DATA.
# =============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PG_HOME="${PG_HOME:-$HOME/.workbuddy-ai/binaries/postgres}"
PG_DATA="${PG_DATA:-$PG_HOME/data}"
PG_LOG="${PG_LOG:-$PG_HOME/server.log}"

# --- Rutas para binarios nativos de Windows ---------------------------------
# Git Bash entrega las rutas en formato POSIX (/c/Users/...). PostgreSQL es un
# ejecutable nativo de Windows y una ruta asi la interpreta relativa a la raiz
# del disco: /c/Users/... acaba siendo C:\c\Users\... , que NO es la misma
# carpeta. Sin convertir, el script arranca (o crea) un cluster distinto y
# vacio, y da la impresion de que la base se vacio. Ya paso una vez.
a_nativo() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        printf '%s' "$1"
    fi
}

PG_DATA_N="$(a_nativo "$PG_DATA")"
PG_LOG_N="$(a_nativo "$PG_LOG")"

# --- Localizar los binarios -------------------------------------------------
if [ -x "$PG_HOME/pgsql/bin/pg_ctl" ] || [ -x "$PG_HOME/pgsql/bin/pg_ctl.exe" ]; then
    PG_BIN="$PG_HOME/pgsql/bin"
elif command -v pg_ctl >/dev/null 2>&1; then
    PG_BIN="$(dirname "$(command -v pg_ctl)")"
else
    cat >&2 <<'FIN'
[start_db] No encuentro pg_ctl.

  Si usas el PostgreSQL portable de este entorno, revisa que exista
  $PG_HOME/pgsql/bin (o define PG_HOME con la ruta correcta).

  Si tienes PostgreSQL instalado en el sistema, asegurate de que pg_ctl
  este en el PATH y define PG_DATA con tu directorio de datos.
FIN
    exit 1
fi

PG_CTL="$PG_BIN/pg_ctl"
PG_ISREADY="$PG_BIN/pg_isready"
[ -x "$PG_CTL" ] || PG_CTL="$PG_BIN/pg_ctl.exe"
[ -x "$PG_ISREADY" ] || PG_ISREADY="$PG_BIN/pg_isready.exe"

# --- Puerto: sale del .env para que no haya discrepancia --------------------
puerto_de_url() {
    [ -f "$RAIZ/.env" ] || return 0
    local url
    url="$(grep -E '^DATABASE_URL=' "$RAIZ/.env" | head -1 | cut -d= -f2- || true)"
    printf '%s' "$url" | sed -nE 's#.*@[^:/@]+:([0-9]+)(/|$).*#\1#p'
}

PUERTO="$(puerto_de_url)"
if [ -z "$PUERTO" ]; then
    PUERTO="$(grep -E '^POSTGRES_PORT=' "$RAIZ/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
fi
PUERTO="${PUERTO:-5432}"

HOST="127.0.0.1"

# --- Acciones ---------------------------------------------------------------
en_marcha() {
    "$PG_ISREADY" -h "$HOST" -p "$PUERTO" >/dev/null 2>&1
}

estado() {
    if en_marcha; then
        echo "[start_db] PostgreSQL responde en $HOST:$PUERTO"
        return 0
    fi
    echo "[start_db] PostgreSQL NO responde en $HOST:$PUERTO"
    return 1
}

arrancar() {
    if en_marcha; then
        echo "[start_db] Ya estaba corriendo en $HOST:$PUERTO. No hago nada."
        return 0
    fi

    if [ ! -d "$PG_DATA" ]; then
        echo "[start_db] No existe el directorio de datos: $PG_DATA" >&2
        echo "[start_db] Define PG_DATA con la ruta correcta." >&2
        exit 1
    fi

    # Guarda contra el peor error posible: arrancar un cluster que no es el
    # nuestro. Si falta PG_VERSION, esto no es un directorio de datos.
    if [ ! -f "$PG_DATA/PG_VERSION" ]; then
        echo "[start_db] $PG_DATA no parece un directorio de datos de PostgreSQL" >&2
        echo "[start_db] (falta PG_VERSION). No arranco nada, para no dejar la" >&2
        echo "[start_db] impresion de que la base se vacio." >&2
        exit 1
    fi

    # Un postmaster.pid huerfano (de un apagon) impide el arranque. Solo se
    # borra si de verdad no queda ningun proceso escuchando, que es el caso
    # porque acabamos de comprobar que no responde.
    if [ -f "$PG_DATA/postmaster.pid" ]; then
        echo "[start_db] Quedo un postmaster.pid de un cierre brusco; lo elimino."
        rm -f "$PG_DATA/postmaster.pid"
    fi

    echo "[start_db] Arrancando PostgreSQL en el puerto $PUERTO..."
    echo "[start_db] Datos: $PG_DATA"

    # El redirect a /dev/null NO es opcional: si no, el servidor hereda el stdout
    # del shell, el pipe nunca se cierra y este comando parece colgado aunque el
    # servidor haya arrancado bien.
    if ! "$PG_CTL" -D "$PG_DATA_N" -l "$PG_LOG_N" -o "-p $PUERTO" -w start >/dev/null 2>&1; then
        echo "[start_db] No arranco. Ultimas lineas del log ($PG_LOG):" >&2
        tail -15 "$PG_LOG" >&2 2>/dev/null || echo "  (no se pudo leer el log)" >&2
        exit 1
    fi

    if en_marcha; then
        echo "[start_db] Listo: PostgreSQL responde en $HOST:$PUERTO"
        echo "[start_db] Siguiente paso:  python scripts/bootstrap_db.py"
    else
        echo "[start_db] Arranco pero no responde en $HOST:$PUERTO." >&2
        echo "[start_db] Revisa $PG_LOG" >&2
        exit 1
    fi
}

detener() {
    if ! en_marcha; then
        echo "[start_db] No estaba corriendo."
        return 0
    fi
    echo "[start_db] Deteniendo PostgreSQL..."
    if ! "$PG_CTL" -D "$PG_DATA_N" -m fast -w stop >/dev/null 2>&1; then
        echo "[start_db] pg_ctl no pudo detener el servidor." >&2
        return 1
    fi

    # pg_ctl -w vuelve cuando el postmaster termina, pero el socket puede tardar
    # un instante mas en cerrarse. Sin esta espera, un `status` inmediato todavia
    # recibe respuesta y parece que el stop no hizo nada.
    local intento
    for intento in $(seq 1 20); do
        if ! en_marcha; then
            echo "[start_db] Detenido."
            return 0
        fi
        sleep 0.5
    done

    echo "[start_db] Aviso: sigue respondiendo en $HOST:$PUERTO tras 10 s." >&2
    return 1
}

case "${1:-start}" in
    start)   arrancar ;;
    status)  estado ;;
    stop)    detener ;;
    restart) detener; arrancar ;;
    *)
        echo "Uso: $0 [start|status|stop|restart]" >&2
        exit 2
        ;;
esac
