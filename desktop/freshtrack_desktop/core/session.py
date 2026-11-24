"""Sesión JWT del usuario (resultado de login/refresh)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from .xml_codec import num


@dataclass
class Session:
    token: str
    jti: str
    usuario: dict = field(default_factory=dict)
    expira_en: float = 0.0  # epoch (segundos) del access token
    refresh_token: str = ""  # renueva el access token hasta el fin de la sesión
    refresh_expira_en: float = 0.0  # epoch (segundos): fin absoluto de la sesión

    DESKTOP_ROLES: ClassVar[set[str]] = {"buyer", "planner", "admin"}

    @classmethod
    def from_auth_response(cls, datos: Any) -> "Session":
        datos = datos if isinstance(datos, dict) else {}
        usuario = datos.get("usuario") if isinstance(datos.get("usuario"), dict) else {}
        return cls(
            token=str(datos.get("token") or ""),
            jti=str(datos.get("jti") or ""),
            usuario=dict(usuario),
            expira_en=time.time() + num(datos.get("expira_en_segundos"), 0.0),
            refresh_token=str(datos.get("refresh_token") or ""),
            refresh_expira_en=time.time() + num(datos.get("refresh_expira_en_segundos"), 0.0),
        )

    @property
    def rol(self) -> str:
        return str(self.usuario.get("rol") or "")

    @property
    def email(self) -> str:
        return str(self.usuario.get("email") or "")

    def can(self, *roles: str) -> bool:
        """True si el rol está en `roles`; admin siempre puede."""
        return self.rol == "admin" or self.rol in roles
