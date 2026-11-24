"""
Registro seguro de dispositivos móviles (app Android).

Tras iniciar sesión la app envía un identificador aleatorio (UUID generado una
sola vez en el teléfono y guardado con la sesión cifrada), el modelo, la
versión de Android y la versión de la app. Se guarda ligado al usuario del JWT
(nunca a un usuario que mande el cliente) en operacion.dispositivo_movil.

  * Volver a registrar el mismo teléfono actualiza sus datos (upsert).
  * Un dispositivo revocado por el administrador no puede re-registrarse: la
    app recibe 403 dispositivo_revocado y cierra la sesión.
  * Alta y revocación se auditan (REGISTER_DEVICE / DEACTIVATE_DEVICE).
"""

from __future__ import annotations

import re

from sqlalchemy import text

from app import auditoria
from app.db import query, transaccion

_RE_TEXTO = re.compile(r"[^\w .,:;()+/#-]", re.UNICODE)


class DispositivoRevocado(PermissionError):
    """El administrador revocó este dispositivo."""


def _texto(valor, largo: int) -> str | None:
    """Texto corto y seguro (sin caracteres de control ni marcado)."""
    if valor is None:
        return None
    limpio = _RE_TEXTO.sub("", str(valor)).strip()[:largo]
    return limpio or None


_CAMPOS = """
    d.id_registro::text AS id_registro, d.id_dispositivo::text AS id_dispositivo,
    d.id_usuario::text AS id_usuario, u.email, d.plataforma, d.modelo, d.version_so,
    d.version_app, d.registrado_en, d.ultimo_registro, d.revocado, d.revocado_en
"""


def registrar(
    *,
    id_dispositivo: str,
    modelo: str | None,
    version_so: str | None,
    version_app: str | None,
    usuario: dict,
    ip: str | None = None,
) -> dict:
    """Alta o actualización del dispositivo del usuario autenticado."""
    datos = {
        "disp": id_dispositivo,
        "u": usuario["id_usuario"],
        "modelo": _texto(modelo, 120),
        "so": _texto(version_so, 40),
        "app": _texto(version_app, 40),
        "ip": (ip or "")[:45] or None,
    }
    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario.get("email")) as conn:
        previo = conn.execute(
            text(
                "SELECT revocado FROM operacion.dispositivo_movil "
                "WHERE id_dispositivo = CAST(:disp AS uuid) AND id_usuario = CAST(:u AS uuid) FOR UPDATE"
            ),
            datos,
        ).mappings().first()
        if previo and previo["revocado"]:
            raise DispositivoRevocado("Este dispositivo fue revocado por un administrador.")
        fila = conn.execute(
            text(
                """
                INSERT INTO operacion.dispositivo_movil
                    (id_dispositivo, id_usuario, modelo, version_so, version_app, ultima_ip)
                VALUES (CAST(:disp AS uuid), CAST(:u AS uuid), :modelo, :so, :app, :ip)
                ON CONFLICT (id_dispositivo, id_usuario) DO UPDATE
                   SET modelo = EXCLUDED.modelo, version_so = EXCLUDED.version_so,
                       version_app = EXCLUDED.version_app, ultima_ip = EXCLUDED.ultima_ip,
                       ultimo_registro = now()
                RETURNING id_registro::text AS id_registro, (xmax = 0) AS nuevo
                """
            ),
            datos,
        ).mappings().first()
    nuevo = bool(fila["nuevo"])
    auditoria.registrar(
        "REGISTER_DEVICE",
        tabla="dispositivo_movil",
        id_registro=fila["id_registro"],
        descripcion=(
            f"{'Alta' if nuevo else 'Actualización'} de dispositivo móvil "
            f"{datos['modelo'] or 'sin modelo'} (Android {datos['so'] or '?'}, app {datos['app'] or '?'})"
        ),
        estado_nuevo={"id_dispositivo": id_dispositivo, "modelo": datos["modelo"],
                      "version_so": datos["so"], "version_app": datos["app"]},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario.get("email"),
        ip=ip,
    )
    return {"id_registro": fila["id_registro"], "id_dispositivo": id_dispositivo, "nuevo": nuevo,
            "estado": "REGISTRADO"}


def listar(*, id_usuario: str | None = None, limite: int = 200) -> list[dict]:
    """Dispositivos de un usuario (o de todos, para el administrador)."""
    filtro = "WHERE d.id_usuario = CAST(:u AS uuid)" if id_usuario else ""
    return query(
        f"""
        SELECT {_CAMPOS}
        FROM operacion.dispositivo_movil d
        JOIN operacion.usuario u ON u.id_usuario = d.id_usuario
        {filtro}
        ORDER BY d.ultimo_registro DESC
        LIMIT :lim
        """,
        lim=limite,
        **({"u": id_usuario} if id_usuario else {}),
    )


def revocar(id_registro: str, *, admin: dict, ip: str | None = None) -> dict | None:
    """Marca el dispositivo como revocado. None si no existe."""
    with transaccion(id_usuario=admin["id_usuario"], usuario_email=admin.get("email")) as conn:
        fila = conn.execute(
            text(
                """
                UPDATE operacion.dispositivo_movil
                   SET revocado = true, revocado_en = COALESCE(revocado_en, now()),
                       revocado_por = COALESCE(revocado_por, CAST(:admin AS uuid))
                 WHERE id_registro = CAST(:id AS uuid)
                RETURNING id_registro::text AS id_registro, id_usuario::text AS id_usuario, modelo
                """
            ),
            {"id": id_registro, "admin": admin["id_usuario"]},
        ).mappings().first()
    if not fila:
        return None
    auditoria.registrar(
        "DEACTIVATE_DEVICE",
        tabla="dispositivo_movil",
        id_registro=id_registro,
        descripcion=f"Dispositivo móvil revocado ({fila['modelo'] or 'sin modelo'}) del usuario {fila['id_usuario']}",
        estado_nuevo={"revocado": True},
        id_usuario=admin["id_usuario"],
        usuario_email=admin.get("email"),
        ip=ip,
    )
    return {"id_registro": fila["id_registro"], "id_usuario": fila["id_usuario"], "revocado": True}

