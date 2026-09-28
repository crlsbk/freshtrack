"""
API JSON de FreshTrack, protegida con JWT.

Todos los endpoints exigen `Authorization: Bearer <token>`; el token se obtiene
en `POST /api/auth/token`. La información que devuelven sale de PostgreSQL, no
de estructuras en memoria.

    GET  /api/kpis                      tablero en JSON
    GET  /api/inventario                inventario por lote
    GET  /api/inventario/fefo           cola FEFO
    GET  /api/alertas                   alertas abiertas
    GET  /api/pronostico                última corrida y su precisión
    GET  /api/reabastecimiento          órdenes y su explicación
    GET  /api/transferencias            sugerencias entre tiendas
    GET  /api/mermas                    mermas recientes y su análisis
    GET  /api/trazabilidad/<id_lote>    ciclo de vida del lote
    POST /api/ventas                    registra una venta con FEFO
    POST /api/mermas                    registra una merma
    POST /api/pronostico/ejecutar       corre el pronóstico
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.db import a_int, sql_error
from app.domain import alertas as motor_alertas
from app.domain import inventario as dom_inv
from app.domain import kpis as motor_kpis
from app.domain import mermas as dom_mermas
from app.domain import pronostico as motor_pron
from app.domain import reabastecimiento as motor_reab
from app.domain import transferencias as motor_tr
from app.domain import ventas as dom_ventas
from app.security import rol_en_token, token_requerido

bp = Blueprint("api", __name__, url_prefix="/api")


def _usuario() -> dict:
    """Identidad del usuario autenticado por token, con la forma que esperan
    las capas de dominio (que usan usuario['id_usuario'] y usuario['email'])."""
    payload = g.jwt_payload
    return {
        "id_usuario": payload["sub"],
        "email": payload.get("email", ""),
        "nombre_completo": payload.get("nombre", ""),
        "rol_clave": payload.get("rol", ""),
        "id_locacion": payload.get("id_locacion"),
    }


def _error(exc: Exception):
    if isinstance(exc, SQLAlchemyError):
        return jsonify({"error": "error_base_datos", "mensaje": sql_error(exc)}), 400
    return jsonify({"error": "solicitud_invalida", "mensaje": str(exc)}), 400


# ===========================================================================
# Lectura
# ===========================================================================
@bp.get("/kpis")
@token_requerido
def api_kpis():
    return jsonify(
        {
            "panel": motor_kpis.panel_principal(),
            "tasa_merma": motor_kpis.tasa_merma(180),
            "alertas": motor_alertas.resumen_alertas(),
            "precision_pronostico": motor_pron.precision_global(),
        }
    )


@bp.get("/inventario")
@token_requerido
def api_inventario():
    id_locacion = a_int(request.args.get("locacion"), 0) or None
    return jsonify(
        {
            "resumen": dom_inv.resumen_inventario(),
            "lotes": dom_inv.inventario_por_lote(id_locacion=id_locacion, limite=500),
        }
    )


@bp.get("/inventario/fefo")
@token_requerido
def api_fefo():
    id_locacion = a_int(request.args.get("locacion"), 0) or None
    return jsonify({"cola": dom_inv.cola_fefo(id_locacion=id_locacion, limite=300)})


@bp.get("/alertas")
@token_requerido
def api_alertas():
    return jsonify(
        {
            "resumen": motor_alertas.resumen_alertas(),
            "alertas": motor_alertas.listar_alertas(
                tipo=request.args.get("tipo") or None,
                severidad=request.args.get("severidad") or None,
                estado=request.args.get("estado") or "ABIERTA",
            ),
            "tipos": motor_alertas.TIPOS,
        }
    )


@bp.get("/pronostico")
@token_requerido
def api_pronostico():
    corrida = motor_pron.ultima_corrida()
    id_run = request.args.get("run") or (corrida["id_run"] if corrida else None)
    return jsonify(
        {
            "corrida": corrida,
            "precision": motor_pron.precision_global(),
            "series": motor_pron.pronostico_por_serie(id_run) if id_run else [],
            "metodos": motor_pron.METODOS,
        }
    )


@bp.get("/reabastecimiento")
@token_requerido
def api_reabastecimiento():
    estado = request.args.get("estado") or "PENDIENTE"
    return jsonify(
        {
            "resumen": motor_reab.resumen_ordenes(),
            "ordenes": motor_reab.listar_ordenes(
                estado=None if estado == "TODAS" else estado
            ),
            "sobreinventario": motor_reab.sobreinventario(),
        }
    )


@bp.get("/transferencias")
@token_requerido
def api_transferencias():
    estado = request.args.get("estado") or "SUGERIDA"
    return jsonify(
        {
            "resumen": motor_tr.resumen_transferencias(),
            "transferencias": motor_tr.listar_transferencias(
                estado=None if estado == "TODAS" else estado
            ),
        }
    )


@bp.get("/mermas")
@token_requerido
def api_mermas():
    return jsonify(
        {
            "resumen": dom_mermas.resumen_mermas(180),
            "mermas": dom_mermas.mermas_recientes(limite=100),
            "causas": dom_mermas.CAUSAS,
        }
    )


@bp.get("/trazabilidad/<id_lote>")
@token_requerido
def api_trazabilidad(id_lote: str):
    detalle = dom_inv.trazabilidad(id_lote)
    if not detalle:
        return jsonify({"error": "lote_no_encontrado"}), 404
    return jsonify(detalle)


# ===========================================================================
# Escritura
# ===========================================================================
@bp.post("/ventas")
@token_requerido
@rol_en_token("admin", "store_manager", "warehouse")
def api_venta():
    datos = request.get_json(silent=True) or request.form
    try:
        id_locacion = int(datos.get("id_locacion"))
        lineas = datos.get("lineas")
        if not lineas:
            lineas = [
                {"id_sku": int(datos.get("id_sku")), "cantidad": float(datos.get("cantidad"))}
            ]
        resultado = dom_ventas.registrar_venta(
            id_locacion=id_locacion, lineas=lineas, usuario=_usuario()
        )
        return jsonify(resultado), 201
    except (TypeError, ValueError) as e:
        return jsonify({"error": "venta_rechazada", "mensaje": str(e)}), 400
    except SQLAlchemyError as e:
        return _error(e)


@bp.post("/mermas")
@token_requerido
@rol_en_token("admin", "store_manager", "warehouse")
def api_merma():
    datos = request.get_json(silent=True) or request.form
    try:
        resultado = dom_mermas.registrar_merma(
            id_lote=datos.get("id_lote"),
            id_locacion=int(datos.get("id_locacion")),
            cantidad=float(datos.get("cantidad")),
            causa=datos.get("causa_merma") or datos.get("causa"),
            observacion=datos.get("observacion"),
            usuario=_usuario(),
        )
        return jsonify(resultado), 201
    except (TypeError, ValueError) as e:
        return jsonify({"error": "merma_rechazada", "mensaje": str(e)}), 400
    except SQLAlchemyError as e:
        return _error(e)


@bp.post("/pronostico/ejecutar")
@token_requerido
@rol_en_token("admin", "planner", "buyer")
def api_pronostico_ejecutar():
    datos = request.get_json(silent=True) or request.form
    try:
        resultado = motor_pron.ejecutar_pronostico(
            usuario=_usuario(),
            metodo=datos.get("metodo", "SUAVIZACION_EXPONENCIAL"),
            horizonte=a_int(datos.get("horizonte"), 7),
            ventana=a_int(datos.get("ventana"), 28),
            alpha=float(datos.get("alpha", 0.30) or 0.30),
            dias_historia=a_int(datos.get("dias_historia"), 120),
            id_locacion=a_int(datos.get("id_locacion"), 0) or None,
        )
        return jsonify(resultado), 201
    except (TypeError, ValueError) as e:
        return jsonify({"error": "pronostico_rechazado", "mensaje": str(e)}), 400
    except SQLAlchemyError as e:
        return _error(e)
