from infra.db import get_connection, transaction
from src.domain.ticket import Ticket
from src.domain.errors import AccesoDenegado


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
            self._registrar_actividad(cursor, ticket_id, usuario.id, "CREADO", "Ticket creado.")
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
        usuario = self._usuario()
        if not usuario.es_supervisor():
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
            cursor.execute("UPDATE tickets SET asignado_a=%s, actualizado_en=CURRENT_TIMESTAMP WHERE id=%s",
                           (agente_id, ticket_id))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo asignar el ticket.")
            self._registrar_actividad(cursor, ticket_id, usuario.id, "ASIGNADO",
                                      f"Ticket asignado al agente #{agente_id}.")

    def cambiar_estado(self, ticket_id, nuevo_estado):
        usuario = self._usuario()
        self._validar_id(ticket_id)
        with transaction(get_connection) as cursor:
            ticket = self._buscar_bloqueado(cursor, ticket_id)
            anterior = ticket.estado
            ticket.cambiar_estado(nuevo_estado, usuario)
            cursor.execute("UPDATE tickets SET estado=%s, actualizado_en=CURRENT_TIMESTAMP WHERE id=%s",
                           (ticket.estado, ticket_id))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo actualizar el ticket.")
            self._registrar_actividad(cursor, ticket_id, usuario.id, "ESTADO",
                                      f"Estado: {anterior} → {ticket.estado}.")

    def obtener_ticket(self, ticket_id):
        usuario = self._usuario()
        self._validar_id(ticket_id)
        with transaction(get_connection) as cursor:
            cursor.execute(f"SELECT {TICKET_COLUMNS} FROM tickets WHERE id=%s", (ticket_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError("Ticket inexistente.")
            ticket = Ticket(**row)
            self._exigir_acceso(ticket, usuario)
            return ticket

    def listar_actividad(self, ticket_id, offset=0):
        usuario = self._usuario()
        self._validar_id(ticket_id)
        self._validar_pagina(offset)
        with transaction(get_connection) as cursor:
            ticket = self._buscar_bloqueado(cursor, ticket_id)
            self._exigir_acceso(ticket, usuario)
            cursor.execute(
                "SELECT a.id, a.tipo, a.contenido, a.creado_en, u.username AS autor "
                "FROM ticket_actividad a JOIN usuarios u ON u.id=a.usuario_id "
                "WHERE a.ticket_id=%s ORDER BY a.id DESC LIMIT 50 OFFSET %s", (ticket_id, offset))
            return cursor.fetchall()

    def agregar_comentario(self, ticket_id, contenido):
        usuario = self._usuario()
        self._validar_id(ticket_id)
        contenido = contenido.strip()
        if not 1 <= len(contenido) <= 5000:
            raise ValueError("El comentario debe tener entre 1 y 5000 caracteres.")
        with transaction(get_connection) as cursor:
            ticket = self._buscar_bloqueado(cursor, ticket_id)
            self._exigir_acceso(ticket, usuario)
            if not ticket.puede_comentarse():
                raise ValueError("No se puede comentar un ticket cerrado.")
            self._registrar_actividad(cursor, ticket_id, usuario.id, "COMENTARIO", contenido)

    @staticmethod
    def _exigir_acceso(ticket, usuario):
        if not (usuario.es_supervisor() or usuario.id in (ticket.creado_por, ticket.asignado_a)):
            raise AccesoDenegado("No tiene acceso a este ticket.")

    @staticmethod
    def _registrar_actividad(cursor, ticket_id, usuario_id, tipo, contenido):
        cursor.execute(
            "INSERT INTO ticket_actividad (ticket_id, usuario_id, tipo, contenido) VALUES (%s, %s, %s, %s)",
            (ticket_id, usuario_id, tipo, contenido))

    @staticmethod
    def _buscar_bloqueado(cursor, ticket_id):
        cursor.execute(f"SELECT {TICKET_COLUMNS} FROM tickets WHERE id=%s FOR UPDATE", (ticket_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Ticket inexistente.")
        return Ticket(**row)
