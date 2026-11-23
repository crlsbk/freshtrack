"""Configuración de la app: URLs de los 8 servicios, timeout y directorio de datos."""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

PUERTOS: dict[str, int] = {
    "auth": 5001,
    "catalog": 5002,
    "inventory": 5003,
    "commercial": 5004,
    "asn": 5005,
    "planning": 5006,
    "alerts": 5007,
    "audit": 5008,
}
HOST_DEFECTO = "http://localhost"
_SECCION = "servidores"


def _normalizar_host(host: str) -> str:
    host = (host or "").strip().rstrip("/")
    if not host:
        return HOST_DEFECTO
    if "://" not in host:
        host = f"http://{host}"
    return host


def urls_para(host: str = HOST_DEFECTO, gateway_url: str = "") -> dict[str, str]:
    """URLs base: todas al gateway si está definido; si no, host:puerto de cada servicio."""
    gateway_url = (gateway_url or "").strip().rstrip("/")
    if gateway_url:
        if "://" not in gateway_url:
            gateway_url = f"http://{gateway_url}"
        return {svc: gateway_url for svc in PUERTOS}
    host = _normalizar_host(host)
    return {svc: f"{host}:{puerto}" for svc, puerto in PUERTOS.items()}


def xsd_dir() -> Path:
    """Directorio de contratos XSD: env FRESHTRACK_XSD_DIR → bundle PyInstaller → repo."""
    env = os.environ.get("FRESHTRACK_XSD_DIR")
    if env:
        return Path(env)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "contracts" / "xsd"
    # desktop/freshtrack_desktop/core/config.py → raíz del repo
    return Path(__file__).resolve().parents[3] / "contracts" / "xsd"


@dataclass
class Settings:
    base_urls: dict[str, str] = field(default_factory=urls_para)
    timeout: float = 15
    data_dir: Path = field(default_factory=lambda: Path.home() / ".freshtrack_desktop")
    host: str = HOST_DEFECTO
    gateway_url: str = ""

    @property
    def config_path(self) -> Path:
        return Path(self.data_dir) / "config.ini"

    def set_servers(self, host: str = HOST_DEFECTO, gateway_url: str = "") -> None:
        """Cambia host/gateway y recalcula las URLs de los 8 servicios."""
        self.host = _normalizar_host(host)
        self.gateway_url = (gateway_url or "").strip().rstrip("/")
        self.base_urls = urls_para(self.host, self.gateway_url)

    @staticmethod
    def xsd_dir() -> Path:
        return xsd_dir()

    @classmethod
    def load(cls, data_dir: Path | None = None) -> "Settings":
        """Lee `data_dir/config.ini`; las variables de entorno tienen prioridad sobre el archivo."""
        s = cls(data_dir=Path(data_dir) if data_dir else Path.home() / ".freshtrack_desktop")
        host, gateway = HOST_DEFECTO, ""
        overrides: dict[str, str] = {}
        cp = configparser.ConfigParser()
        try:
            cp.read(s.config_path, encoding="utf-8")
        except configparser.Error:
            cp = configparser.ConfigParser()
        if cp.has_section(_SECCION):
            sec = cp[_SECCION]
            host = sec.get("host", host)
            gateway = sec.get("gateway_url", gateway)
            try:
                s.timeout = float(sec.get("timeout", s.timeout))
            except ValueError:
                pass
        if cp.has_section("urls"):
            overrides = {k: v.rstrip("/") for k, v in cp["urls"].items() if k in PUERTOS and v.strip()}

        env_gateway = os.environ.get("FRESHTRACK_GATEWAY_URL", "").strip()
        env_host = os.environ.get("FRESHTRACK_HOST", "").strip()
        if env_gateway:
            gateway, overrides = env_gateway, {}
        elif env_host:
            host, gateway, overrides = env_host, "", {}

        s.set_servers(host, gateway)
        s.base_urls.update(overrides)
        return s

    def save(self) -> None:
        cp = configparser.ConfigParser()
        cp[_SECCION] = {"host": self.host, "gateway_url": self.gateway_url, "timeout": str(self.timeout)}
        calculadas = urls_para(self.host, self.gateway_url)
        extra = {k: v for k, v in self.base_urls.items() if calculadas.get(k) != v}
        if extra:
            cp["urls"] = extra
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as fh:
            cp.write(fh)
