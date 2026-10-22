class ErrorPersistencia(RuntimeError):
    """Error de almacenamiento que puede mostrarse sin exponer detalles SQL."""


class AccesoDenegado(ValueError):
    """El usuario autenticado no puede acceder al recurso solicitado."""
