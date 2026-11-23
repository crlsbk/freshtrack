"""Errores que la app muestra al usuario (mismos campos que <error_response> del servidor)."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Error devuelto por un microservicio o detectado por el cliente."""

    def __init__(
        self,
        status: int,
        error: str,
        mensaje: str,
        correlation_id: str = "",
        detalles: Any = None,
    ) -> None:
        super().__init__(mensaje)
        self.status = int(status or 0)
        self.error = error
        self.mensaje = mensaje
        self.correlation_id = correlation_id
        self.detalles = detalles

    def __str__(self) -> str:
        return self.mensaje

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status={self.status}, error={self.error!r}, mensaje={self.mensaje!r})"


class ServiceUnavailable(ApiError):
    """No se pudo hablar con el servicio (conexión rechazada, timeout, DNS...)."""

    def __init__(self, service: str, mensaje: str | None = None, correlation_id: str = "", detalles: Any = None) -> None:
        super().__init__(
            0,
            "servicio_no_disponible",
            mensaje or f"Servicio {service} no disponible",
            correlation_id,
            detalles,
        )
        self.service = service


class XmlContractError(ApiError):
    """XML mal formado, que no es XML, o que no cumple su contrato XSD / raíz esperada."""

    def __init__(
        self,
        mensaje: str,
        detalles: list[str] | None = None,
        *,
        status: int = 0,
        correlation_id: str = "",
    ) -> None:
        super().__init__(status, "xml_invalido", mensaje, correlation_id, list(detalles or []))
