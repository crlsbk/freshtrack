"""
Mantenimiento de agregados materializados (sql/08_optimizacion.sql).

`analitica.v_demanda_diaria` = histórico materializado ∪ ventas posteriores al
corte en vivo. La vista siempre es correcta, pero es rápida solo si el histórico
está al día: si el corte quedó en un día anterior (no hubo refresco nocturno) o
el agregado está "sucio" (se escribieron ventas con fecha retroactiva), parte de
la consulta vuelve a agregar `venta_detalle` en vivo.

Este módulo:
  * `necesita_refresco()`   — lectura barata de analitica.agregado_refresco.
  * `refrescar_si_necesario()` — refresca bajo bloqueo distribuido Redis (y el
    advisory lock de la propia función SQL), así N workers no lo repiten.
  * `iniciar_mantenimiento_en_segundo_plano()` — hilo daemon de la app web que
    revisa cada N minutos. Sustituye a un cron si la VM no tiene uno.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from app import db
from app.services import cache_service

logger = logging.getLogger(__name__)

_hilo: threading.Thread | None = None
_lock_hilo = threading.Lock()


def disponible() -> bool:
    """True si la base ya tiene la optimización 08 aplicada."""
    try:
        return bool(db.escalar("SELECT to_regprocedure('analitica.fn_refrescar_agregados()') IS NOT NULL"))
    except Exception:  # noqa: BLE001
        return False


def necesita_refresco() -> bool:
    fila = db.one(
        """
        SELECT (corte < CURRENT_DATE::timestamptz) OR sucio AS necesita
        FROM analitica.agregado_refresco
        WHERE nombre = 'mv_demanda_diaria_hist'
        """
    )
    return bool(fila and fila["necesita"])


def refrescar(forzar: bool = False) -> int | None:
    """Refresca la demanda materializada. Devuelve ms o None si no hizo nada."""
    if not forzar and not necesita_refresco():
        return None
    with cache_service.bloqueo_distribuido("agregados:demanda_diaria", timeout_segundos=600) as token:
        # Sin Redis (token None) seguimos: la función SQL serializa con advisory lock.
        if token is None and cache_service.get_redis_client() is not None:
            return None  # otro worker lo está refrescando
        if not forzar and not necesita_refresco():
            return None
        ms = db.escribir("SELECT analitica.fn_refrescar_agregados()")
        logger.info("Demanda diaria materializada refrescada en %s ms", ms)
        # Las agregaciones cacheadas que dependen de la demanda pueden cambiar.
        for patron in ("web:forecast:*", "web:reab:*", "web:desp:*"):
            try:
                cache_service.invalidar_patron(patron)
            except Exception:  # noqa: BLE001
                pass
        return int(ms) if ms is not None else 0


def refrescar_si_necesario() -> int | None:
    try:
        if not disponible():
            return None
        return refrescar(forzar=False)
    except Exception as exc:  # noqa: BLE001 — nunca tumbar la app por esto
        logger.warning("No se pudo refrescar la demanda materializada: %s", exc)
        return None


def _bucle(intervalo: int) -> None:
    # Pequeño desfase para no competir con el arranque de la app.
    time.sleep(15)
    while True:
        refrescar_si_necesario()
        time.sleep(intervalo)


def iniciar_mantenimiento_en_segundo_plano() -> None:
    """Arranca (una vez por proceso) el hilo que mantiene el histórico al día."""
    global _hilo
    if os.getenv("AGREGADOS_AUTO_REFRESCO", "true").strip().lower() in ("0", "false", "no"):
        return
    if os.getenv("FLASK_TESTING") or os.getenv("PYTEST_CURRENT_TEST"):
        return
    with _lock_hilo:
        if _hilo is not None and _hilo.is_alive():
            return
        intervalo = max(60, int(os.getenv("AGREGADOS_INTERVALO_SEG", "600")))
        _hilo = threading.Thread(target=_bucle, args=(intervalo,), name="agregados-refresco", daemon=True)
        _hilo.start()
