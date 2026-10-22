"""Operaciones de Redis: sesiones, denylist, caché, contadores, temporales con TTL y bloqueos."""

from __future__ import annotations

import time

from app.services import cache_service as cs


def test_sesion_con_ttl_e_indice_por_usuario(redis_falso):
    assert cs.crear_sesion_redis("s1", {"id_usuario": "u1", "rol": "admin"}, ttl_segundos=120)
    assert cs.sesion_activa("s1") is True
    assert 0 < redis_falso.ttl("session:s1") <= 120
    assert cs.listar_sesiones_usuario("u1") == ["s1"]
    assert cs.eliminar_sesion_redis("s1")
    assert cs.sesion_activa("s1") is False


def test_denylist_jwt(redis_falso):
    assert not cs.esta_jwt_revocado("j1")
    cs.revocar_jwt("j1", ttl_segundos=300)
    assert cs.esta_jwt_revocado("j1")
    assert cs.contar_tokens_revocados() == 1
    assert redis_falso.ttl("jwt:denylist:j1") > 0


def test_cache_aside_e_invalidacion_por_patron(redis_falso):
    cs.set_json("catalog:products:a", {"x": 1}, ttl_segundos=60)
    cs.set_json("catalog:products:b", {"x": 2}, ttl_segundos=60)
    cs.set_json("catalog:locations:all", [1], ttl_segundos=60)
    assert cs.get_json("catalog:products:a") == {"x": 1}
    assert cs.invalidar_patron("catalog:products:*") == 2
    assert cs.get_json("catalog:products:a") is None
    assert cs.get_json("catalog:locations:all") == [1]


def test_contadores_de_operacion(redis_falso):
    cs.incrementar_contador("inventory", "reserve_success")
    cs.incrementar_contador("inventory", "reserve_success")
    contadores = cs.obtener_contadores("inventory")
    assert any(v == 2 for k, v in contadores.items() if "reserve_success" in k)


def test_temporal_se_consume_una_sola_vez(redis_falso):
    cs.guardar_temporal("pos_cart", "c1", {"lineas": [1]}, ttl_segundos=900)
    assert 0 < cs.obtener_ttl("temp:pos_cart:c1") <= 900
    assert cs.consumir_temporal("pos_cart", "c1") == {"lineas": [1]}
    assert cs.consumir_temporal("pos_cart", "c1") is None


def test_bloqueo_distribuido_exclusivo(redis_falso):
    token = cs.adquirir_bloqueo("inv:loc:1", timeout_segundos=5)
    assert token
    assert cs.adquirir_bloqueo("inv:loc:1") is None
    assert not cs.liberar_bloqueo("inv:loc:1", "token-ajeno")
    assert cs.liberar_bloqueo("inv:loc:1", token)
    with cs.bloqueo_distribuido("inv:loc:1") as t:
        assert t is not None


def test_rate_limit_ventana_fija(redis_falso):
    resultados = [cs.verificar_rate_limit("ip:1", limite=3, ventana_segundos=60) for _ in range(4)]
    assert [r[0] for r in resultados] == [True, True, True, False]
    assert resultados[2][1] == 0


def test_sin_redis_no_reintenta_en_cada_llamada(monkeypatch):
    """Si Redis no responde, se espera SEGUNDOS_REINTENTO antes de volver a pagar el timeout."""
    monkeypatch.setattr(cs, "_client", None)
    monkeypatch.setattr(cs, "_ultimo_fallo", 0.0)
    monkeypatch.setattr(cs.Config, "REDIS_HOST", "127.0.0.1")
    monkeypatch.setattr(cs.Config, "REDIS_PORT", 1)
    assert cs.get_redis_client() is None
    inicio = time.perf_counter()
    for _ in range(20):
        assert cs.get_redis_client() is None
    assert time.perf_counter() - inicio < 0.1
    # Degradación controlada: las operaciones no lanzan excepción.
    assert cs.esta_jwt_revocado("x") is False
    assert cs.sesion_activa("x") is None
