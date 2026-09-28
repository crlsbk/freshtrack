"""
Página pública.

La ruta `/` NO manda directo al login: muestra una landing que explica qué es
FreshTrack, el problema del desperdicio de alimentos, los objetivos, los
beneficios y cómo funciona el sistema. Si ya hay sesión iniciada, se redirige
al panel que corresponde al rol.
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, session, url_for

from app.navegacion import ruta_inicial

bp = Blueprint("publico", __name__)


@bp.route("/")
def inicio():
    if "user_id" in session:
        return redirect(url_for(ruta_inicial(session.get("role", ""))))

    # Cifras de contexto (públicas, sin información empresarial sensible)
    contexto = {
        "dato_fao": "1,050 millones de toneladas",
        "dato_fao_texto": (
            "de alimentos se desperdician cada año en el mundo, cerca de un tercio "
            "de todo lo que se produce (FAO)."
        ),
        "dato_merma_retail": "En el comercio minorista de perecederos, entre el 2% y el 4% "
        "de lo recibido termina como merma, y la mayor parte se debe a caducidad.",
    }

    # Si la base está disponible, mostramos el número real del sistema.
    try:
        from app.db import one

        real = one(
            """
            SELECT COALESCE(SUM(cantidad_disponible), 0) AS unidades,
                   COUNT(DISTINCT id_sku)                AS skus,
                   COUNT(DISTINCT id_locacion)           AS locaciones,
                   COUNT(*) FILTER (WHERE clasificacion IN ('CRITICO','VENCIDO')) AS criticos
            FROM operacion.v_inventario_lote
            WHERE cantidad_disponible > 0
            """
        )
        if real:
            contexto["cifras_sistema"] = real
    except Exception:
        # La landing no debe caerse si la base todavía no está lista.
        pass

    return render_template("landing.html", **contexto)
