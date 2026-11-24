"""Suite de carga (tests/load): curva, clasificación, saturación, recuperación, ranking e importador."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.load import analisis
from tests.load.analisis import Fase


# --- Clasificación de respuestas -------------------------------------------------
@pytest.mark.parametrize("status,clase", [
    (200, "ok"), (201, "ok"), (409, "negocio"), (422, "negocio"), (429, "limite"),
    (400, "error_prueba"), (403, "error_prueba"), (500, "fallo"), (503, "fallo"), (0, "fallo"),
])
def test_clasificar(status, clase):
    assert analisis.clasificar(status) == clase


def test_timeout_es_fallo_real():
    assert analisis.clasificar(None, TimeoutError()) == "fallo"


def test_percentil_rango_mas_cercano():
    valores = list(range(1, 101))
    assert analisis.percentil(valores, 95) == 95
    assert analisis.percentil(valores, 99) == 99
    assert analisis.percentil([], 95) == 0.0


# --- Curva -----------------------------------------------------------------------
def test_curva_por_defecto():
    f = analisis.FASES_RENDIMIENTO
    assert [x.usuarios for x in f] == [20, 60, 120, 200, 20]
    assert analisis.fase_en(f, 10)[0].nombre == "LINEA_BASE"
    assert analisis.fase_en(f, 61)[0].nombre == "NORMAL"
    assert analisis.fase_en(f, 200)[0].nombre == "PICO"
    assert analisis.fase_en(f, 250)[0].nombre == "RECUPERACION"
    assert analisis.fase_en(f, analisis.duracion_total(f)) is None


def test_parsear_fases():
    assert analisis.parsear_fases("BASE:30:10,PICO:60:50") == (Fase("BASE", 30, 10), Fase("PICO", 60, 50))
    assert analisis.parsear_fases("5:20")[0] == Fase("FASE_1", 5, 20)
    with pytest.raises(ValueError):
        analisis.parsear_fases("x")


# --- Colector ---------------------------------------------------------------------
def _alimentar(col, fase, segundo0, segundos, rps, ms, clase="ok", vus=10, nombre="/a"):
    for s in range(segundo0, segundo0 + segundos):
        for _ in range(rps):
            col.registrar(segundo=s, fase=fase, vus=vus, metodo="GET", nombre=nombre, ms=ms, status=200,
                          clase=clase)


def test_colector_agrega_por_fase_endpoint_y_errores():
    col = analisis.Colector()
    _alimentar(col, "LINEA_BASE", 0, 10, 5, 100.0)
    col.registrar(segundo=3, fase="LINEA_BASE", vus=10, metodo="POST", nombre="/b", ms=900.0, status=500,
                  clase="fallo", mensaje="error_interno")
    fases = col.fases((Fase("LINEA_BASE", 10, 10),))
    assert fases[0]["peticiones"] == 51 and fases[0]["rps"] == 5.1 and fases[0]["fallo"] == 1
    assert {e["endpoint"] for e in col.endpoints()} == {"/a", "/b"}
    assert col.lista_errores()[0]["status"] == 500
    assert len(col.serie()) == 10
    col.sumar("ventas_registradas")
    assert col.negocio["ventas_registradas"] == 1


# --- Saturación / recuperación / ranking ----------------------------------------------
def _fase(nombre, vus, rps, p95, fallo=0.0, limite=0.0):
    return {"fase": nombre, "usuarios": vus, "rps": rps, "p95_ms": p95, "pct_fallo": fallo, "pct_limite": limite}


def test_sin_saturacion_cuando_escala_lineal():
    fases = [_fase("A", 20, 10, 200), _fase("B", 60, 30, 250), _fase("C", 120, 60, 300)]
    assert analisis.detectar_saturacion(fases)["saturado"] is False


def test_satura_por_throughput_plano():
    fases = [_fase("A", 20, 10, 200), _fase("B", 60, 30, 260), _fase("C", 120, 31, 400)]
    r = analisis.detectar_saturacion(fases)
    assert r["saturado"] and r["fase"] == "C" and "ΔRPS/ΔVU" in r["motivos"][0]


def test_satura_por_latencia_o_errores():
    assert analisis.detectar_saturacion([_fase("A", 20, 10, 200), _fase("B", 60, 30, 1800)])["fase"] == "B"
    assert analisis.detectar_saturacion([_fase("A", 20, 10, 200), _fase("B", 60, 30, 300, fallo=3)])["fase"] == "B"
    assert analisis.detectar_saturacion([_fase("A", 20, 10, 200), _fase("B", 60, 30, 300, limite=8)])["fase"] == "B"


def _serie(fase, desde, p95s, fallos=None):
    fallos = fallos or [0] * len(p95s)
    return [{"segundo": desde + i, "fase": fase, "p95_ms": p, "fallo": f} for i, (p, f) in enumerate(zip(p95s, fallos))]


def test_recuperacion_mide_segundos_hasta_volver_a_la_base():
    serie = _serie("PICO", 0, [2000] * 5) + _serie("RECUPERACION", 5, [1500] * 7 + [250] * 15)
    r = analisis.medir_recuperacion(serie, "RECUPERACION", p95_base=200)
    assert r["recuperado"] and r["segundos"] == 7


def test_no_recuperado():
    serie = _serie("RECUPERACION", 0, [900] * 20)
    r = analisis.medir_recuperacion(serie, "RECUPERACION", p95_base=200)
    assert r["recuperado"] is False and r["p95_final_ms"] == 900


def test_top_lentos_ordena_por_p95_y_descarta_muestras_pequenas():
    eps = [
        {"endpoint": "/rapido", "peticiones": 100, "p95_ms": 50, "p99_ms": 80},
        {"endpoint": "/lento", "peticiones": 100, "p95_ms": 900, "p99_ms": 1200},
        {"endpoint": "/raro", "peticiones": 2, "p95_ms": 5000, "p99_ms": 5000},
    ]
    assert [e["endpoint"] for e in analisis.top_lentos(eps)] == ["/lento", "/rapido"]


# --- Importador (sin base de datos) ---------------------------------------------------
def test_importador_lee_carpeta_de_corrida(tmp_path: Path):
    from scripts.locust_importar import leer_corrida

    (tmp_path / "config.json").write_text(json.dumps(
        {"run_id": "r1", "escenario": "ventas", "host": "https://x", "commit": "abc"}), encoding="utf-8")
    (tmp_path / "resumen.json").write_text(json.dumps({
        "global": {"usuarios_max": 30, "peticiones": 900, "rps": 3.0, "p95_ms": 120},
        "saturacion": {"saturado": False}, "recuperacion": {"recuperado": None}}), encoding="utf-8")
    (tmp_path / "fases.json").write_text(json.dumps([{"fase": "VENTAS_CONSTANTES", "usuarios": 30}]), encoding="utf-8")
    (tmp_path / "endpoints.json").write_text(json.dumps([{"metodo": "GET", "endpoint": "/a", "peticiones": 1}]), encoding="utf-8")
    (tmp_path / "serie_segundos.csv").write_text("segundo,fase,usuarios\n0,VENTAS_CONSTANTES,30\n", encoding="utf-8")
    datos = leer_corrida(tmp_path)
    assert datos["corrida"]["run_id"] == "r1" and datos["corrida"]["usuarios_max"] == 30
    assert datos["fases"][0]["orden"] == 0
    assert datos["endpoints"][0]["fase"] == "TOTAL"
    assert len(datos["serie"]) == 1


def test_sql_11_define_esquema_pruebas():
    sql = (Path(__file__).resolve().parents[2] / "sql" / "11_pruebas_carga.sql").read_text(encoding="utf-8")
    for tabla in ("pruebas.corrida", "pruebas.fase", "pruebas.endpoint_metrica", "pruebas.error", "pruebas.serie_segundo"):
        assert f"CREATE TABLE IF NOT EXISTS {tabla}" in sql
