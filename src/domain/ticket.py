from datetime import datetime


class Ticket:
    """Ticket y reglas del ciclo de atención."""

    ABIERTO = "ABIERTO"
    EN_PROCESO = "EN_PROCESO"
    EN_ESPERA = "EN_ESPERA"
    RESUELTO = "RESUELTO"
    CERRADO = "CERRADO"
    ESTADOS_VALIDOS = (ABIERTO, EN_PROCESO, EN_ESPERA, RESUELTO, CERRADO)
    TRANSICIONES = {
        ABIERTO: (EN_PROCESO,),
        EN_PROCESO: (EN_ESPERA, RESUELTO),
        EN_ESPERA: (EN_PROCESO, RESUELTO),
        RESUELTO: (CERRADO, EN_PROCESO),
        CERRADO: (EN_PROCESO,),
    }

    def __init__(self, id, titulo, descripcion, estado, creado_por,
                 asignado_a=None, creado_en=None, actualizado_en=None):
        self.id = id
        self.titulo = titulo
        self.descripcion = descripcion
        self.estado = estado.upper()
        if self.estado not in self.ESTADOS_VALIDOS:
            raise ValueError("Estado del ticket inválido.")
        self.creado_por = creado_por
        self.asignado_a = asignado_a
        self.creado_en = creado_en or datetime.now()
        self.actualizado_en = actualizado_en

    def esta_cerrado(self):
        return self.estado == self.CERRADO

    def esta_abierto(self):
        return self.estado == self.ABIERTO

    def puede_modificarse(self):
        return not self.esta_cerrado()

    def puede_comentarse(self):
        return not self.esta_cerrado()

    def cambiar_estado(self, nuevo_estado, usuario):
        if not (usuario.es_supervisor() or
                (usuario.es_agente() and usuario.id == self.asignado_a)):
            raise ValueError("Solo el agente asignado o un supervisor puede cambiar el estado.")
        nuevo_estado = nuevo_estado.strip().upper()
        if self.esta_cerrado() and not usuario.es_supervisor():
            raise ValueError("Solo un supervisor puede reabrir un ticket cerrado.")
        if nuevo_estado not in self.TRANSICIONES[self.estado]:
            raise ValueError(f"Transición no permitida: {self.estado} → {nuevo_estado}.")
        self.estado = nuevo_estado
        self.actualizado_en = datetime.now()

    def asignar_a(self, agente_id):
        if self.esta_cerrado():
            raise ValueError("No se puede asignar un ticket cerrado.")
        self.asignado_a = agente_id
        self.actualizado_en = datetime.now()

    def __str__(self):
        return f"Ticket #{self.id}: {self.titulo} ({self.estado})"

    def __repr__(self):
        return self.__str__()
