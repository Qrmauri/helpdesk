import hashlib
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, Mock, patch

import pymysql

from infra.db import get_connection, transaction
from services.auth_service import AuthService
from services.ticket_service import TicketService
from src.domain.errors import ErrorPersistencia
from src.domain.ticket import Ticket
from src.domain.usuario import Usuario
from ui.menu import Menu


def usuario(role="PUBLICADOR", user_id=1):
    return Usuario(user_id, "usuario", "usuario@example.com", "", role)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.auth = AuthService()
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.connection = patch("services.auth_service.get_connection", return_value=self.conn)
        self.connection.start()
        self.addCleanup(self.connection.stop)

    def test_login_maps_role_name_to_domain_user(self):
        self.cursor.fetchone.return_value = {
            "id": 1, "username": "usuario", "email": "usuario@example.com",
            "password_hash": hashlib.sha256(b"clave").hexdigest(),
            "role": "SUPERVISOR",
        }
        result = self.auth.login("usuario", "clave")
        self.assertIsInstance(result, Usuario)
        self.assertTrue(result.es_supervisor())

    def test_failed_login_raises_and_clears_previous_session(self):
        self.auth.usuario_actual = usuario("SUPERVISOR")
        self.cursor.fetchone.return_value = None
        with self.assertRaises(ValueError):
            self.auth.login("ausente", "incorrecta")
        self.assertIsNone(self.auth.usuario_actual)

    def test_public_registration_rejects_supervisor(self):
        with self.assertRaises(ValueError):
            self.auth.registrar("usuario", "u@example.com", "clave-segura", "SUPERVISOR")

    def test_password_has_random_salt(self):
        self.assertNotEqual(self.auth.hash_password("misma-clave"),
                            self.auth.hash_password("misma-clave"))

    def test_password_verification_accepts_correct_and_rejects_wrong_password(self):
        stored = self.auth.hash_password("clave-segura")
        self.assertTrue(self.auth.verificar_password("clave-segura", stored))
        self.assertFalse(self.auth.verificar_password("otra-clave", stored))
        self.assertFalse(self.auth.verificar_password("clave", "scrypt$invalido$hash"))

    def test_legacy_password_is_migrated_after_successful_login(self):
        self.cursor.fetchone.return_value = {
            "id": 1, "username": "usuario", "email": "u@example.com",
            "password_hash": hashlib.sha256(b"clave").hexdigest(), "role": "PUBLICADOR",
        }
        self.auth.login("usuario", "clave")
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("UPDATE usuarios SET password_hash", sql)
        self.assertTrue(params[0].startswith("scrypt$"))
        self.conn.commit.assert_called_once()

    def test_wrong_password_does_not_migrate_or_open_session(self):
        self.cursor.fetchone.return_value = {
            "id": 1, "username": "usuario", "email": "u@example.com",
            "password_hash": hashlib.sha256(b"clave").hexdigest(), "role": "PUBLICADOR",
        }
        with self.assertRaises(ValueError):
            self.auth.login("usuario", "incorrecta")
        self.assertIsNone(self.auth.usuario_actual)
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.conn.rollback.assert_called_once()

    def test_registration_validates_inputs_before_connecting(self):
        for username, email, password in [
            ("", "u@example.com", "clave-segura"),
            ("usuario", "sin-arroba", "clave-segura"),
            ("usuario", "u@example.com", "corta"),
            ("usuario", "u@example.com", " " * 10),
        ]:
            with self.subTest(username=username, email=email), self.assertRaises(ValueError):
                self.auth.registrar(username, email, password)
        self.assertFalse(self.conn.cursor.called)

    def test_duplicate_user_rolls_back(self):
        self.cursor.fetchone.side_effect = [{"id": 1}, {"id": 5}]
        with self.assertRaisesRegex(ValueError, "ya existe"):
            self.auth.registrar("usuario", "u@example.com", "clave-segura")
        self.conn.commit.assert_not_called()
        self.conn.rollback.assert_called_once()

    def test_duplicate_race_is_reported_as_validation_error(self):
        self.cursor.fetchone.side_effect = [{"id": 1}, None]
        self.cursor.execute.side_effect = [None, None, pymysql.IntegrityError(1062, "duplicate")]
        with self.assertRaisesRegex(ValueError, "ya existe"):
            self.auth.registrar("usuario", "u@example.com", "clave-segura")
        self.conn.rollback.assert_called_once()

    def test_publisher_cannot_change_roles(self):
        self.auth.usuario_actual = usuario()
        with self.assertRaises(ValueError):
            self.auth.cambiar_rol(2, "SUPERVISOR")

    def test_supervisor_cannot_demote_self(self):
        self.auth.usuario_actual = usuario("SUPERVISOR")
        self.auth.obtener_usuario_actual = Mock(return_value=self.auth.usuario_actual)
        with self.assertRaises(ValueError):
            self.auth.cambiar_rol(1, "PUBLICADOR")

    def test_supervisor_cannot_demote_agent_with_active_tickets(self):
        self.auth.usuario_actual = usuario("SUPERVISOR")
        self.auth.obtener_usuario_actual = Mock(return_value=self.auth.usuario_actual)
        self.cursor.fetchone.side_effect = [{"id": 1}, {"id": 2}, {"id": 99}]
        with self.assertRaisesRegex(ValueError, "Reasigne"):
            self.auth.cambiar_rol(2, "PUBLICADOR")
        self.conn.commit.assert_not_called()

    def test_role_revoked_in_database_is_not_kept_in_session(self):
        self.auth.usuario_actual = usuario("SUPERVISOR")
        self.cursor.fetchone.return_value = dict(
            id=1, username="usuario", email="u@example.com", password_hash="", role="PUBLICADOR")
        with self.assertRaisesRegex(ValueError, "ya no tiene permisos"):
            self.auth.listar_usuarios()
        self.assertFalse(self.auth.usuario_actual.es_supervisor())


class TicketTests(unittest.TestCase):
    def setUp(self):
        self.auth = Mock(usuario_actual=usuario("SUPERVISOR"))
        self.auth.obtener_usuario_actual.side_effect = lambda: self.auth.usuario_actual
        self.service = TicketService(self.auth)

    def test_no_session_cannot_list(self):
        self.auth.usuario_actual = None
        with self.assertRaises(ValueError):
            self.service.listar_mis_tickets()

    def test_publisher_cannot_list_every_ticket(self):
        self.auth.usuario_actual = usuario()
        with self.assertRaises(ValueError):
            self.service.listar_todos()

    def test_missing_ticket_cannot_be_assigned(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [{"id": 2, "role": "AGENTE"}, None]
        with patch("services.ticket_service.get_connection", return_value=conn):
            with self.assertRaises(ValueError):
                self.service.asignar_ticket(999, 2)
        conn.commit.assert_not_called()

    def test_ticket_list_uses_named_mapping(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{
            "descripcion": "Detalle", "id": 5, "titulo": "Prueba", "estado": "ABIERTO",
            "creado_por": 1, "asignado_a": None, "creado_en": None, "actualizado_en": None,
        }]
        with patch("services.ticket_service.get_connection", return_value=conn):
            tickets = self.service.listar_todos()
        self.assertEqual(tickets[0].creado_por, 1)
        self.assertEqual(tickets[0].descripcion, "Detalle")

    def test_create_failure_is_not_reported_as_success(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = pymysql.OperationalError(2006, "lost")
        with patch("services.ticket_service.get_connection", return_value=conn):
            with self.assertRaises(ErrorPersistencia):
                self.service.crear_ticket("Título", "Descripción")
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_empty_ticket_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.crear_ticket("   ", "Descripción")

    def test_assignment_rejects_publisher_as_destination(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {"id": 2, "role": "PUBLICADOR"}
        with patch("services.ticket_service.get_connection", return_value=conn):
            with self.assertRaises(ValueError):
                self.service.asignar_ticket(1, 2)
        conn.commit.assert_not_called()

    def test_assignment_requires_actual_update(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [{"id": 2, "role": "AGENTE"}, ticket_row()]
        cursor.rowcount = 0
        with patch("services.ticket_service.get_connection", return_value=conn):
            with self.assertRaisesRegex(ValueError, "No se pudo asignar"):
                self.service.asignar_ticket(5, 2)
        conn.commit.assert_not_called()

    def test_closed_ticket_cannot_be_assigned(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [{"id": 2, "role": "AGENTE"}, ticket_row("CERRADO")]
        with patch("services.ticket_service.get_connection", return_value=conn):
            with self.assertRaisesRegex(ValueError, "cerrado"):
                self.service.asignar_ticket(5, 2)
        conn.commit.assert_not_called()

    def test_creation_uses_authenticated_author(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.lastrowid = 42
        with patch("services.ticket_service.get_connection", return_value=conn):
            self.assertEqual(self.service.crear_ticket("Título", "Descripción"), 42)
        self.assertEqual(cursor.execute.call_args.args[1][-1], self.auth.usuario_actual.id)
        conn.commit.assert_called_once()

    def test_successful_assignment_commits(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [{"id": 2, "role": "AGENTE"}, ticket_row()]
        cursor.rowcount = 1
        with patch("services.ticket_service.get_connection", return_value=conn):
            self.service.asignar_ticket(5, 2)
        conn.commit.assert_called_once()
        self.assertEqual(cursor.execute.call_args.args[1][0], 2)

    def test_status_change_persists_and_commits(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ticket_row()
        cursor.rowcount = 1
        with patch("services.ticket_service.get_connection", return_value=conn):
            self.service.cambiar_estado(5, "EN_PROCESO")
        self.assertEqual(cursor.execute.call_args.args[1][0], "EN_PROCESO")
        conn.commit.assert_called_once()


def ticket_row(estado="ABIERTO", asignado_a=None):
    return dict(id=5, titulo="Título", descripcion="Descripción", estado=estado,
                creado_por=1, asignado_a=asignado_a, creado_en=None, actualizado_en=None)


class TicketDomainTests(unittest.TestCase):
    def test_assigned_agent_can_resolve_and_close(self):
        ticket = Ticket(**ticket_row(asignado_a=2))
        agent = usuario("AGENTE", 2)
        for state in ("EN_PROCESO", "EN_ESPERA", "RESUELTO", "CERRADO"):
            ticket.cambiar_estado(state, agent)
        self.assertTrue(ticket.esta_cerrado())
        self.assertIsNotNone(ticket.actualizado_en)

    def test_other_agent_cannot_change_status(self):
        ticket = Ticket(**ticket_row(asignado_a=2))
        with self.assertRaises(ValueError):
            ticket.cambiar_estado("EN_PROCESO", usuario("AGENTE", 3))

    def test_publisher_cannot_change_status(self):
        with self.assertRaises(ValueError):
            Ticket(**ticket_row()).cambiar_estado("EN_PROCESO", usuario())

    def test_invalid_transition_is_rejected_even_for_supervisor(self):
        with self.assertRaises(ValueError):
            Ticket(**ticket_row()).cambiar_estado("CERRADO", usuario("SUPERVISOR"))

    def test_closed_ticket_only_reopens_to_in_progress_by_supervisor(self):
        ticket = Ticket(**ticket_row("CERRADO", 2))
        with self.assertRaises(ValueError):
            ticket.cambiar_estado("EN_PROCESO", usuario("AGENTE", 2))
        with self.assertRaises(ValueError):
            ticket.cambiar_estado("ABIERTO", usuario("SUPERVISOR"))
        ticket.cambiar_estado("EN_PROCESO", usuario("SUPERVISOR"))
        self.assertEqual(ticket.estado, "EN_PROCESO")


class DatabaseTests(unittest.TestCase):
    def test_credentials_are_required(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            get_connection()

    def test_query_error_rolls_back_and_hides_sql_details(self):
        conn = MagicMock()
        with self.assertRaises(ErrorPersistencia) as caught:
            with transaction(lambda: conn):
                raise pymysql.ProgrammingError(1146, "private schema detail")
        self.assertNotIn("private schema detail", str(caught.exception))
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_commit_error_is_not_success(self):
        conn = MagicMock()
        conn.commit.side_effect = pymysql.OperationalError(2006, "lost")
        with self.assertRaises(ErrorPersistencia):
            with transaction(lambda: conn):
                pass
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_lost_connection_during_rollback_stays_a_safe_error(self):
        conn = MagicMock()
        conn.rollback.side_effect = pymysql.OperationalError(2006, "private detail")
        with self.assertRaises(ErrorPersistencia) as caught:
            with transaction(lambda: conn):
                raise pymysql.OperationalError(2006, "private detail")
        self.assertNotIn("private detail", str(caught.exception))
        conn.close.assert_called_once()


class MenuTests(unittest.TestCase):
    def test_failed_registration_does_not_announce_success(self):
        auth = Mock()
        auth.registrar.side_effect = ValueError("Usuario existente.")
        output = io.StringIO()
        with patch("builtins.input", side_effect=["usuario", "u@example.com"]), \
                patch("ui.menu.getpass", return_value="clave-segura"), redirect_stdout(output):
            Menu(auth, Mock()).registrar()
        self.assertNotIn("creado exitosamente", output.getvalue())
        self.assertIn("Usuario existente", output.getvalue())

    def test_failed_login_returns_to_menu(self):
        auth = Mock()
        auth.login.side_effect = ValueError("Credenciales inválidas.")
        with patch("builtins.input", return_value="usuario"), \
                patch("ui.menu.getpass", return_value="incorrecta"), redirect_stdout(io.StringIO()):
            Menu(auth, Mock()).login()

    def test_database_failure_in_menu_does_not_announce_created_ticket(self):
        auth = Mock()
        service = Mock()
        service.crear_ticket.side_effect = ErrorPersistencia("No disponible.")
        output = io.StringIO()
        with patch("builtins.input", side_effect=["1", "Título", "Descripción", "0"]), redirect_stdout(output):
            Menu(auth, service).mostrar_menu_usuario(usuario())
        self.assertNotIn("creado exitosamente", output.getvalue())
        self.assertIn("No disponible", output.getvalue())

    def test_supervisor_ticket_view_uses_domain_attributes(self):
        service = Mock()
        service.listar_todos.return_value = [Ticket(**ticket_row())]
        output = io.StringIO()
        with redirect_stdout(output):
            Menu(Mock(), service).ver_todos_tickets()
        self.assertIn("Creado por: #1", output.getvalue())

    def test_assignment_validation_message_is_preserved(self):
        service = Mock()
        service.asignar_ticket.side_effect = ValueError("Ticket inexistente.")
        output = io.StringIO()
        with patch("builtins.input", side_effect=["4", "99", "2", "0"]), redirect_stdout(output):
            Menu(Mock(), service).mostrar_menu_usuario(usuario("SUPERVISOR"))
        self.assertIn("Ticket inexistente", output.getvalue())
        self.assertNotIn("asignado correctamente", output.getvalue())


if __name__ == "__main__":
    unittest.main()
