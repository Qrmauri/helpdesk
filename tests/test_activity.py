import unittest
from unittest.mock import MagicMock, Mock, patch

from services.ticket_service import TicketService
from src.domain.usuario import Usuario


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.user = Usuario(1, "autor", "autor@example.com", "", "PUBLICADOR")
        self.auth = Mock(usuario_actual=self.user)
        self.auth.obtener_usuario_actual.return_value = self.user
        self.service = TicketService(self.auth)
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = dict(
            id=8, titulo="Impresora", descripcion="No imprime", estado="ABIERTO",
            creado_por=1, asignado_a=2, creado_en=None, actualizado_en=None)
        patcher = patch("services.ticket_service.get_connection", return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_author_can_comment_and_commit(self):
        self.service.agregar_comentario(8, "  Ya reinicié el equipo.  ")
        self.assertEqual(self.cursor.execute.call_args.args[1],
                         (8, 1, "COMENTARIO", "Ya reinicié el equipo."))
        self.conn.commit.assert_called_once()

    def test_unrelated_user_cannot_read_or_comment(self):
        self.user.id = 99
        for operation in (lambda: self.service.obtener_ticket(8),
                          lambda: self.service.listar_actividad(8),
                          lambda: self.service.agregar_comentario(8, "Texto")):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                operation()
        self.conn.commit.assert_not_called()

    def test_closed_ticket_rejects_comment(self):
        self.cursor.fetchone.return_value["estado"] = "CERRADO"
        with self.assertRaises(ValueError):
            self.service.agregar_comentario(8, "Un comentario")
        self.conn.commit.assert_not_called()

    def test_empty_and_oversized_comments_are_rejected(self):
        for value in ("   ", "x" * 5001):
            with self.subTest(value=len(value)), self.assertRaises(ValueError):
                self.service.agregar_comentario(8, value)
        self.conn.commit.assert_not_called()

    def test_creation_records_history_in_same_transaction(self):
        self.cursor.lastrowid = 8
        self.assertEqual(self.service.crear_ticket("Impresora", "No imprime"), 8)
        self.assertIn("INSERT INTO ticket_actividad", self.cursor.execute.call_args.args[0])
        self.assertEqual(self.cursor.execute.call_args.args[1][2], "CREADO")
        self.conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
