"""
Bitácora local de actividad del usuario (JSON por línea, 1 MB × 3 archivos).

Las acciones registradas en esta ejecución quedan pendientes y `sync_remote(api)`
las envía a svc-audit (`POST /api/v1/audit/log`, raíz `audit_log_request`). svc-audit toma
el usuario del JWT, así que solo se envían las del usuario de la sesión vigente; las de
otros usuarios (p. ej. el planner cuya sesión fue revocada) se quedan solo en el archivo local.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .errors import ApiError, XmlContractError

MAX_BYTES = 1_000_000
BACKUPS = 3
_PREFIJO = "DESKTOP_"


def accion_remota(action: str) -> str:
    """Sanea la acción al patrón del XSD `[A-Za-z_]{3,40}` con prefijo DESKTOP_."""
    limpia = re.sub(r"[^A-Za-z_]", "_", action or "").upper().strip()
    if limpia.startswith(_PREFIJO):
        limpia = limpia[len(_PREFIJO):]
    return (_PREFIJO + (limpia or "ACCION"))[:40]


class ActivityLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._usuario = ""
        self._pendientes: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._handler = RotatingFileHandler(self.path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger = logging.getLogger(f"freshtrack_desktop.activity.{id(self)}")
        self._logger.propagate = False
        self._logger.setLevel(logging.INFO)
        self._logger.addHandler(self._handler)

    def set_user(self, email: str | None) -> None:
        self._usuario = email or ""

    def record(self, action: str, detail: str, ok: bool = True) -> None:
        entrada = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "usuario": self._usuario,
            "accion": action,
            "detalle": detail,
            "ok": bool(ok),
        }
        with self._lock:
            self._logger.info(json.dumps(entrada, ensure_ascii=False))
            self._handler.flush()
            self._pendientes.append(entrada)

    def tail(self, n: int = 200) -> list[dict]:
        """Últimas `n` entradas (más antigua primero), incluyendo los archivos rotados."""
        lineas: list[str] = []
        archivos = [self.path.with_name(f"{self.path.name}.{i}") for i in range(BACKUPS, 0, -1)] + [self.path]
        with self._lock:
            for archivo in archivos:
                try:
                    lineas.extend(archivo.read_text(encoding="utf-8").splitlines())
                except OSError:
                    continue
        filas: list[dict] = []
        for linea in lineas[-n:] if n > 0 else []:
            try:
                fila = json.loads(linea)
            except ValueError:
                continue
            if isinstance(fila, dict):
                filas.append(fila)
        return filas

    def sync_remote(self, api: Any) -> int:
        """Envía las acciones pendientes a svc-audit. Nunca lanza; devuelve cuántas se enviaron."""
        sesion = getattr(api, "session", None)
        if sesion is None:
            return 0
        dueño = str(getattr(sesion, "email", "") or "").lower()
        enviados = 0
        while True:
            with self._lock:
                if not self._pendientes:
                    break
                entrada = self._pendientes[0]
                if not dueño or str(entrada.get("usuario") or "").lower() != dueño:
                    self._pendientes.pop(0)  # de otro usuario: no se registra con este JWT
                    continue
            descripcion = (entrada.get("detalle") or entrada.get("accion") or "-")
            if not entrada.get("ok", True):
                descripcion = f"[ERROR] {descripcion}"
            cuerpo = {
                "accion": accion_remota(str(entrada.get("accion", ""))),
                "tabla": "desktop",
                "descripcion": str(descripcion)[:500],
            }
            enviado = True
            try:
                api.call("audit", "POST", "/api/v1/audit/log", body=cuerpo,
                         body_root="audit_log_request", body_xsd="audit_log_request")
            except ApiError as exc:
                definitivo = isinstance(exc, XmlContractError) or (400 <= exc.status < 500 and exc.status != 401)
                if not definitivo:
                    break  # servicio caído o sesión vencida: se reintenta en la próxima sincronización
                enviado = False  # el servidor la rechaza siempre: se descarta para no bloquear la cola
            except Exception:
                break
            with self._lock:
                if self._pendientes and self._pendientes[0] is entrada:
                    self._pendientes.pop(0)
            enviados += int(enviado)
        return enviados

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._handler.close()
