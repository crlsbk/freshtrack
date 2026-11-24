"""
Análisis de una corrida de Locust (funciones puras, sin red ni Locust).

Lo usan el locustfile (colector en vivo) y el runner (reporte final), y se
prueba por separado en tests/unit/test_locust_suite.py.

Clases de respuesta (base de «Errores»):
  ok          2xx
  negocio     409 / 422: regla de negocio esperada (stock insuficiente,
              transición inválida). No es un fallo del sistema.
  limite      429: contrapresión del rate limit (saturación controlada).
  error_prueba otro 4xx: la prueba pidió algo inválido (se debe corregir).
  fallo       5xx, timeout o error de conexión: fallo REAL del sistema.
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from dataclasses import dataclass, field

CLASES = ("ok", "negocio", "limite", "error_prueba", "fallo")


def clasificar(status: int | None, excepcion: BaseException | None = None) -> str:
    if excepcion is not None and not status:
        return "fallo"  # timeout / conexión
    if status is None or status == 0:
        return "fallo"
    if 200 <= status < 300:
        return "ok"
    if status in (409, 422):
        return "negocio"
    if status == 429:
        return "limite"
    if 400 <= status < 500:
        return "error_prueba"
    return "fallo"


def percentil(valores: list[float], p: float) -> float:
    """Percentil por rango más cercano (el que usa Locust); 0 si no hay datos."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    k = max(0, min(len(ordenados) - 1, math.ceil(p / 100.0 * len(ordenados)) - 1))
    return float(ordenados[k])


# --- Curva de carga ----------------------------------------------------------
@dataclass(frozen=True)
class Fase:
    nombre: str
    segundos: int
    usuarios: int


FASES_RENDIMIENTO = (
    Fase("LINEA_BASE", 60, 20),
    Fase("NORMAL", 60, 60),
    Fase("ALTA", 60, 120),
    Fase("PICO", 60, 200),
    Fase("RECUPERACION", 90, 20),
)

FASES_VENTAS = (Fase("VENTAS_CONSTANTES", 20 * 60, 30),)


def parsear_fases(texto: str) -> tuple[Fase, ...]:
    """'NOMBRE:segundos:usuarios,...' o 'segundos:usuarios,...' → fases."""
    fases = []
    for i, parte in enumerate(p for p in texto.split(",") if p.strip()):
        trozos = [t.strip() for t in parte.split(":")]
        if len(trozos) == 2:
            nombre, seg, usr = f"FASE_{i + 1}", trozos[0], trozos[1]
        elif len(trozos) == 3:
            nombre, seg, usr = trozos
        else:
            raise ValueError(f"Fase inválida: {parte!r} (use nombre:segundos:usuarios)")
        fases.append(Fase(nombre.upper(), int(seg), int(usr)))
    if not fases:
        raise ValueError("Se requiere al menos una fase.")
    return tuple(fases)


def fase_en(fases: tuple[Fase, ...], t: float) -> tuple[Fase, float] | None:
    """Fase activa en el segundo t y el inicio de esa fase; None al terminar."""
    inicio = 0.0
    for f in fases:
        if t < inicio + f.segundos:
            return f, inicio
        inicio += f.segundos
    return None


def duracion_total(fases: tuple[Fase, ...]) -> int:
    return sum(f.segundos for f in fases)


# --- Colector en vivo --------------------------------------------------------
@dataclass
class _Acumulado:
    tiempos: list[float] = field(default_factory=list)
    clases: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    bytes: int = 0

    def agregar(self, ms: float, clase: str, tam: int) -> None:
        self.tiempos.append(ms)
        self.clases[clase] += 1
        self.bytes += tam or 0

    def resumen(self, segundos: float | None = None) -> dict:
        n = len(self.tiempos)
        fallos = self.clases.get("fallo", 0)
        r = {
            "peticiones": n,
            "media_ms": round(sum(self.tiempos) / n, 1) if n else 0.0,
            "p50_ms": round(percentil(self.tiempos, 50), 1),
            "p95_ms": round(percentil(self.tiempos, 95), 1),
            "p99_ms": round(percentil(self.tiempos, 99), 1),
            "max_ms": round(max(self.tiempos), 1) if n else 0.0,
            **{c: int(self.clases.get(c, 0)) for c in CLASES},
            "pct_fallo": round(100.0 * fallos / n, 2) if n else 0.0,
            "pct_limite": round(100.0 * self.clases.get("limite", 0) / n, 2) if n else 0.0,
        }
        if segundos:
            r["rps"] = round(n / segundos, 2)
        return r


class Colector:
    """Acumula cada petición por segundo, por fase y por (fase, endpoint)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.por_segundo: dict[int, _Acumulado] = defaultdict(_Acumulado)
        self.vus_por_segundo: dict[int, int] = {}
        self.fase_por_segundo: dict[int, str] = {}
        self.por_fase: dict[str, _Acumulado] = defaultdict(_Acumulado)
        self.por_endpoint: dict[tuple[str, str], _Acumulado] = defaultdict(_Acumulado)
        self.por_fase_endpoint: dict[tuple[str, str, str], _Acumulado] = defaultdict(_Acumulado)
        self.errores: dict[tuple[str, str, int, str], int] = defaultdict(int)
        self.segundos_fase: dict[str, set[int]] = defaultdict(set)
        self.negocio: dict[str, float] = defaultdict(float)  # contadores de negocio (ventas, unidades…)

    def registrar(
        self, *, segundo: int, fase: str, vus: int, metodo: str, nombre: str,
        ms: float, status: int | None, clase: str, tam: int = 0, mensaje: str = "",
    ) -> None:
        with self._lock:
            self.por_segundo[segundo].agregar(ms, clase, tam)
            self.vus_por_segundo[segundo] = vus
            self.fase_por_segundo[segundo] = fase
            self.segundos_fase[fase].add(segundo)
            self.por_fase[fase].agregar(ms, clase, tam)
            self.por_endpoint[(metodo, nombre)].agregar(ms, clase, tam)
            self.por_fase_endpoint[(fase, metodo, nombre)].agregar(ms, clase, tam)
            if clase != "ok":
                self.errores[(metodo, nombre, int(status or 0), (mensaje or "")[:160])] += 1

    def sumar(self, clave: str, valor: float = 1.0) -> None:
        with self._lock:
            self.negocio[clave] += valor

    # -- salidas ---------------------------------------------------------------
    def serie(self) -> list[dict]:
        filas = []
        for s in sorted(self.por_segundo):
            r = self.por_segundo[s].resumen(1.0)
            filas.append({"segundo": s, "fase": self.fase_por_segundo.get(s, ""),
                          "usuarios": self.vus_por_segundo.get(s, 0), **r})
        return filas

    def fases(self, orden: tuple[Fase, ...]) -> list[dict]:
        salida = []
        for f in orden:
            acum = self.por_fase.get(f.nombre)
            if not acum:
                continue
            segs = max(1, len(self.segundos_fase[f.nombre]))
            salida.append({"fase": f.nombre, "usuarios": f.usuarios, "segundos": f.segundos,
                           **acum.resumen(segs)})
        return salida

    def endpoints(self) -> list[dict]:
        return [{"metodo": m, "endpoint": n, **a.resumen()} for (m, n), a in self.por_endpoint.items()]

    def fase_endpoints(self) -> list[dict]:
        return [{"fase": f, "metodo": m, "endpoint": n, **a.resumen()}
                for (f, m, n), a in self.por_fase_endpoint.items()]

    def lista_errores(self) -> list[dict]:
        return sorted(
            ({"metodo": m, "endpoint": n, "status": st, "mensaje": msg, "conteo": c}
             for (m, n, st, msg), c in self.errores.items()),
            key=lambda e: -e["conteo"],
        )

    def global_(self) -> dict:
        total = _Acumulado()
        for a in self.por_fase.values():
            total.tiempos.extend(a.tiempos)
            for c, v in a.clases.items():
                total.clases[c] += v
        segs = max(1, len(self.por_segundo))
        r = total.resumen(segs)
        r["rps_pico"] = max((len(a.tiempos) for a in self.por_segundo.values()), default=0)
        r["usuarios_max"] = max(self.vus_por_segundo.values(), default=0)
        return r


# --- Saturación, recuperación y ranking -----------------------------------------
UMBRAL_P95_MS = 1500.0
UMBRAL_FALLO_PCT = 1.0
UMBRAL_LIMITE_PCT = 5.0
UMBRAL_EFICIENCIA = 0.15


def detectar_saturacion(fases: list[dict]) -> dict:
    """
    Primera fase (en orden de carga creciente) donde el sistema deja de escalar:
      - eficiencia marginal ΔRPS/ΔVU < 15 % de la eficiencia de la línea base, o
      - p95 > 1,500 ms, o fallos reales > 1 %, o 429 > 5 %.
    """
    if not fases:
        return {"saturado": False, "motivo": "sin datos"}
    base = fases[0]
    eficiencia_base = (base.get("rps", 0) / base["usuarios"]) if base.get("usuarios") else 0
    previo = base
    for f in fases:
        motivos = []
        if f["p95_ms"] > UMBRAL_P95_MS:
            motivos.append(f"p95 {f['p95_ms']:.0f} ms > {UMBRAL_P95_MS:.0f} ms")
        if f["pct_fallo"] > UMBRAL_FALLO_PCT:
            motivos.append(f"fallos reales {f['pct_fallo']:.2f} % > {UMBRAL_FALLO_PCT:.0f} %")
        if f["pct_limite"] > UMBRAL_LIMITE_PCT:
            motivos.append(f"429 {f['pct_limite']:.2f} % > {UMBRAL_LIMITE_PCT:.0f} %")
        if f is not base and f["usuarios"] > previo["usuarios"] and eficiencia_base > 0:
            marginal = (f.get("rps", 0) - previo.get("rps", 0)) / (f["usuarios"] - previo["usuarios"])
            if marginal < UMBRAL_EFICIENCIA * eficiencia_base:
                motivos.append(
                    f"ΔRPS/ΔVU {marginal:.3f} < 15 % de la línea base ({eficiencia_base:.3f})"
                )
        if motivos:
            return {"saturado": True, "fase": f["fase"], "usuarios": f["usuarios"], "motivos": motivos,
                    "rps": f.get("rps"), "p95_ms": f["p95_ms"]}
        if f["usuarios"] >= previo["usuarios"]:
            previo = f
    return {"saturado": False, "motivo": f"escaló hasta {max(f['usuarios'] for f in fases)} VU sin saturar"}


def medir_recuperacion(
    serie: list[dict], fase_recuperacion: str, p95_base: float, ventana: int = 10, factor: float = 1.35
) -> dict:
    """
    Segundos desde el inicio de la fase de recuperación hasta que una ventana
    deslizante de `ventana` s vuelve a p95 ≤ factor × p95 de línea base y 0 % de
    fallos reales. Usa los p95 por segundo (aproximación conservadora: el máximo
    de la ventana).
    """
    puntos = [s for s in serie if s["fase"] == fase_recuperacion]
    if not puntos or p95_base <= 0:
        return {"recuperado": False, "motivo": "sin datos de recuperación"}
    objetivo = factor * p95_base
    inicio = puntos[0]["segundo"]
    for i in range(0, max(1, len(puntos) - ventana + 1)):
        tramo = puntos[i:i + ventana]
        if len(tramo) < min(ventana, len(puntos)):
            break
        if max(t["p95_ms"] for t in tramo) <= objetivo and sum(t["fallo"] for t in tramo) == 0:
            return {"recuperado": True, "segundos": tramo[0]["segundo"] - inicio,
                    "objetivo_p95_ms": round(objetivo, 1)}
    ultimo = puntos[-ventana:]
    return {"recuperado": False, "objetivo_p95_ms": round(objetivo, 1),
            "p95_final_ms": max(t["p95_ms"] for t in ultimo),
            "fallos_finales": sum(t["fallo"] for t in ultimo)}


def top_lentos(endpoints: list[dict], n: int = 10, minimo: int = 5) -> list[dict]:
    """Ranking por p95 (y p99 de desempate) de endpoints con al menos `minimo` peticiones."""
    candidatos = [e for e in endpoints if e["peticiones"] >= minimo]
    return sorted(candidatos, key=lambda e: (-e["p95_ms"], -e["p99_ms"]))[:n]
