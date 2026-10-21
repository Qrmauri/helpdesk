from infra.db import get_connection, transaction
from src.domain.ticket import Ticket


TICKET_COLUMNS = (
    "id, titulo, descripcion, estado, id_usuario AS creado_por, "
    "asignado_a, creado_en, actualizado_en"
)


class TicketService:
    """Opera con la sesión autenticada; el cliente no elige el autor ni sus permisos."""

    def __init__(self, auth_service):
        self.auth = auth_service

    def _usuario(self):
        if self.auth.usuario_actual is None:
            raise ValueError("Debe iniciar sesión.")
        return self.auth.obtener_usuario_actual()

    @staticmethod
    def _validar_id(value):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError("El ID debe ser un número entero positivo.")

    @staticmethod
    def _validar_pagina(offset):
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Página inválida.")

    def crear_ticket(self, titulo, descripcion):
        usuario = self._usuario()
        titulo, descripcion = titulo.strip(), descripcion.strip()
        if not 1 <= len(titulo) <= 200:
            raise ValueError("El título debe tener entre 1 y 200 caracteres.")
        if not 1 <= len(descripcion) <= 10000:
            raise ValueError("La descripción debe tener entre 1 y 10000 caracteres.")
        with transaction(get_connection) as cursor:
            cursor.execute(
                "INSERT INTO tickets (titulo, descripcion, estado, id_usuario) VALUES (%s, %s, %s, %s)",
                (titulo, descripcion, Ticket.ABIERTO, usuario.id))
            ticket_id = cursor.lastrowid
        return ticket_id

    def listar_mis_tickets(self, offset=0):
        usuario = self._usuario()
        self._validar_pagina(offset)
        with transaction(get_connection) as cursor:
            cursor.execute(
                f"SELECT {TICKET_COLUMNS} FROM tickets WHERE id_usuario=%s OR asignado_a=%s "
                "ORDER BY id DESC LIMIT 50 OFFSET %s", (usuario.id, usuario.id, offset))
            return [Ticket(**row) for row in cursor.fetchall()]

    def listar_todos(self, offset=0):
        if not self._usuario().es_supervisor():
            raise ValueError("Solo un supervisor puede ver todos los tickets.")
        self._validar_pagina(offset)
        with transaction(get_connection) as cursor:
            cursor.execute(f"SELECT {TICKET_COLUMNS} FROM tickets ORDER BY id DESC LIMIT 50 OFFSET %s", (offset,))
            return [Ticket(**row) for row in cursor.fetchall()]

    def asignar_ticket(self, ticket_id, agente_id):
        if not self._usuario().es_supervisor():
            raise ValueError("Solo un supervisor puede asignar tickets.")
        self._validar_id(ticket_id)
        self._validar_id(agente_id)
        with transaction(get_connection) as cursor:
            cursor.execute("SELECT u.id, r.nombre AS role FROM usuarios u "
                           "JOIN roles r ON r.id=u.id_rol WHERE u.id=%s FOR UPDATE", (agente_id,))
            agente = cursor.fetchone()
            if agente is None or agente["role"] != "AGENTE":
                raise ValueError("El usuario de destino no existe o no es un agente.")
            ticket = self._buscar_bloqueado(cursor, ticket_id)
            if ticket.asignado_a == agente_id:
                raise ValueError("El ticket ya está asignado a ese agente.")
            ticket.asignar_a(agente_id)
            cursor.execute("UPDATE tickets SET asignado_a=%s, actualizado_en=%s WHERE id=%s",
                           (agente_id, ticket.actualizado_en, ticket_id))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo asignar el ticket.")

    def cambiar_estado(self, ticket_id, nuevo_estado):
        usuario = self._usuario()
        self._validar_id(ticket_id)
        with transaction(get_connection) as cursor:
            ticket = self._buscar_bloqueado(cursor, ticket_id)
            ticket.cambiar_estado(nuevo_estado, usuario)
            cursor.execute("UPDATE tickets SET estado=%s, actualizado_en=%s WHERE id=%s",
                           (ticket.estado, ticket.actualizado_en, ticket_id))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo actualizar el ticket.")

    @staticmethod
    def _buscar_bloqueado(cursor, ticket_id):
        cursor.execute(f"SELECT {TICKET_COLUMNS} FROM tickets WHERE id=%s FOR UPDATE", (ticket_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Ticket inexistente.")
        return Ticket(**row)
