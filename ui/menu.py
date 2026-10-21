from getpass import getpass

from src.domain.errors import ErrorPersistencia
from src.domain.ticket import Ticket


class Menu:
    """Interfaz de consola. Los servicios validan los permisos y las operaciones."""

    def __init__(self, auth_service, ticket_service):
        self.auth = auth_service
        self.ticket = ticket_service

    def mostrar_menu_principal(self):
        try:
            while True:
                print("\n===== HELPDESK - SURSOPORTE LTDA. =====")
                print("1. Iniciar sesión\n2. Registrarse\n3. Salir")
                opcion = input("Seleccione una opción: ").strip()
                if opcion == "1":
                    self.login()
                elif opcion == "2":
                    self.registrar()
                elif opcion == "3":
                    print("¡Hasta pronto!")
                    return
                else:
                    print("Opción inválida.")
        except (EOFError, KeyboardInterrupt):
            print("\nSesión finalizada.")
        finally:
            self.auth.logout()

    def login(self):
        print("\n--- INICIAR SESIÓN ---")
        username = input("Usuario: ")
        password = getpass("Contraseña: ")
        try:
            usuario = self.auth.login(username, password)
        except (ValueError, ErrorPersistencia) as exc:
            print(f"Error: {exc}")
            return
        print(f"Bienvenido, {usuario.username} ({usuario.role}).")
        try:
            self.mostrar_menu_usuario(usuario)
        finally:
            self.auth.logout()

    def registrar(self):
        print("\n--- REGISTRO COMO PUBLICADOR ---")
        username = input("Usuario: ")
        email = input("Email: ")
        password = getpass("Contraseña (10 a 128 caracteres): ")
        try:
            self.auth.registrar(username, email, password)
            print("Usuario creado exitosamente.")
        except (ValueError, ErrorPersistencia) as exc:
            print(f"Error: {exc}")

    def mostrar_menu_usuario(self, usuario):
        while True:
            print(f"\n===== {usuario.role} - {usuario.username} =====")
            print("1. Crear ticket\n2. Ver mis tickets")
            if usuario.es_supervisor():
                print("3. Ver todos los tickets\n4. Asignar ticket a agente")
                print("6. Ver usuarios\n7. Cambiar rol de usuario")
            if usuario.es_agente() or usuario.es_supervisor():
                print("5. Cambiar estado de ticket")
            print("0. Cerrar sesión")
            opcion = input("Seleccione una opción: ").strip()
            try:
                if opcion == "0":
                    return
                elif opcion == "1":
                    self.crear_ticket()
                elif opcion == "2":
                    self.ver_mis_tickets()
                elif opcion == "3" and usuario.es_supervisor():
                    self.ver_todos_tickets()
                elif opcion == "4" and usuario.es_supervisor():
                    self.asignar_ticket()
                elif opcion == "5" and (usuario.es_agente() or usuario.es_supervisor()):
                    self.cambiar_estado()
                elif opcion == "6" and usuario.es_supervisor():
                    self.ver_usuarios()
                elif opcion == "7" and usuario.es_supervisor():
                    self.cambiar_rol()
                else:
                    print("Opción inválida.")
            except (ValueError, ErrorPersistencia) as exc:
                print(f"Error: {exc}")

    def crear_ticket(self):
        titulo = input("Título: ")
        descripcion = input("Descripción: ")
        ticket_id = self.ticket.crear_ticket(titulo, descripcion)
        print(f"Ticket #{ticket_id} creado exitosamente.")

    def ver_mis_tickets(self):
        self._listar_tickets(self.ticket.listar_mis_tickets)

    def ver_todos_tickets(self):
        self._listar_tickets(self.ticket.listar_todos)

    @staticmethod
    def _listar_tickets(listar):
        offset = 0
        while True:
            tickets = listar(offset=offset)
            if not tickets:
                print("No hay más tickets.")
                return
            for ticket in tickets:
                print(f"\n{ticket}\n  Descripción: {ticket.descripcion}")
                print(f"  Creado por: #{ticket.creado_por} | Asignado a: {ticket.asignado_a or 'Sin asignar'}")
                print(f"  Creado: {ticket.creado_en} | Actualizado: {ticket.actualizado_en or 'Sin cambios'}")
            if len(tickets) < 50 or input("N para siguiente página; Enter para volver: ").strip().upper() != "N":
                return
            offset += 50

    def asignar_ticket(self):
        ticket_id = self._leer_id("ID del ticket: ")
        agente_id = self._leer_id("ID del agente (consulte Ver usuarios): ")
        self.ticket.asignar_ticket(ticket_id, agente_id)
        print(f"Ticket #{ticket_id} asignado correctamente.")

    def cambiar_estado(self):
        ticket_id = self._leer_id("ID del ticket: ")
        print("Estados: " + ", ".join(Ticket.ESTADOS_VALIDOS))
        estado = input("Nuevo estado: ")
        self.ticket.cambiar_estado(ticket_id, estado)
        print(f"Estado del ticket #{ticket_id} actualizado.")

    def ver_usuarios(self):
        offset = 0
        while True:
            usuarios = self.auth.listar_usuarios(offset=offset)
            if not usuarios:
                print("No hay más usuarios.")
                return
            for usuario in usuarios:
                print(f"#{usuario['id']} | {usuario['username']} | {usuario['role']}")
            if len(usuarios) < 50 or input("N para siguiente página; Enter para volver: ").strip().upper() != "N":
                return
            offset += 50

    def cambiar_rol(self):
        user_id = self._leer_id("ID del usuario: ")
        role = input("Nuevo rol (PUBLICADOR, AGENTE, SUPERVISOR): ").strip().upper()
        self.auth.cambiar_rol(user_id, role)
        print("Rol actualizado.")

    @staticmethod
    def _leer_id(prompt):
        try:
            value = int(input(prompt))
        except ValueError:
            raise ValueError("El ID debe ser un número entero positivo.") from None
        if value <= 0:
            raise ValueError("El ID debe ser un número entero positivo.")
        return value
