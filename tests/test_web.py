import unittest
from unittest.mock import patch

from db_fixture import TestDatabase
from services.auth_service import AuthService
from web import create_app


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "Prueba-segura123"
        cls.password_hash = AuthService.hash_password(cls.password)

    def setUp(self):
        self.db = TestDatabase(self.password_hash)
        self.addCleanup(self.db.close)
        for name in ("services.auth_service.get_connection", "services.ticket_service.get_connection"):
            patcher = patch(name, side_effect=self.db.connect)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "clave-exclusiva-pruebas-32-caracteres", "RATELIMIT_ENABLED": False})
        self.client = self.app.test_client()

    def sign_in(self, user_id=1, client=None):
        with (client or self.client).session_transaction() as session:
            session["user_id"] = user_id
            session["csrf_token"] = "token-pruebas"

    def post(self, path, data=None, client=None):
        target = client or self.client
        with target.session_transaction() as session:
            token = session.get("csrf_token", "")
        return target.post(path, data={**(data or {}), "csrf_token": token})

    def create_ticket(self):
        self.sign_in()
        response = self.post("/tickets/nuevo", {"titulo": "Impresora sin conexión", "descripcion": "No imprime desde recepción."})
        self.assertEqual(response.status_code, 302)
        return int(response.location.rsplit("/", 1)[1])

    def test_login_page_and_security_headers(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertIn("HttpOnly", response.headers.get("Set-Cookie", ""))
        self.assertIn("SameSite=Lax", response.headers.get("Set-Cookie", ""))

    def test_protected_page_redirects_to_login(self):
        response = self.client.get("/tickets")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    def test_mutation_without_csrf_is_rejected(self):
        self.sign_in()
        response = self.client.post("/tickets/nuevo", data={"titulo": "Prueba", "descripcion": "Detalle"})
        self.assertEqual(response.status_code, 400)

    def test_invalid_unicode_csrf_does_not_cause_server_error(self):
        self.sign_in()
        response = self.client.post("/logout", data={"csrf_token": "inválido"})
        self.assertEqual(response.status_code, 400)

    def test_login_rate_limit_is_enforced(self):
        app = create_app({"TESTING": True, "SECRET_KEY": "clave-pruebas-rate-limit-32-caracteres", "RATELIMIT_ENABLED": True})
        client = app.test_client()
        client.get("/login")
        for _ in range(10):
            response = self.post("/login", {"username": "ausente", "password": "incorrecta"}, client=client)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post("/login", {"username": "ausente", "password": "incorrecta"}, client=client).status_code, 429)

    def test_login_stores_only_identity_and_rotates_csrf(self):
        self.client.get("/login")
        response = self.post("/login", {"username": "publicador", "password": self.password})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 1)
            self.assertNotIn("password", session)
            self.assertNotIn("role", session)

    def test_registration_ignores_privileged_role_from_browser(self):
        self.client.get("/registro")
        response = self.post("/registro", {
            "username": "nuevo", "email": "nuevo@example.com", "password": self.password, "role": "SUPERVISOR"})
        self.assertEqual(response.status_code, 302)
        with self.db.connect().raw as conn:
            row = conn.execute("SELECT id_rol FROM usuarios WHERE username='nuevo'").fetchone()
            self.assertEqual(row[0], 1)

    def test_create_comment_and_detail_escape_html(self):
        ticket_id = self.create_ticket()
        text = '<script>alert("xss")</script>'
        response = self.post(f"/tickets/{ticket_id}/comentarios", {"contenido": text})
        self.assertEqual(response.status_code, 302)
        detail = self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(detail.status_code, 200)
        html = detail.get_data(as_text=True)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn(text, html)
        self.assertIn("Ticket creado.", html)

    def test_other_user_cannot_access_detail_or_comment(self):
        ticket_id = self.create_ticket()
        self.sign_in(4)
        self.assertEqual(self.client.get(f"/tickets/{ticket_id}").status_code, 403)
        self.assertEqual(self.post(f"/tickets/{ticket_id}/comentarios", {"contenido": "Intrusión"}).status_code, 403)

    def test_full_assignment_status_and_history_flow(self):
        ticket_id = self.create_ticket()
        self.sign_in(3)
        self.assertEqual(self.post(f"/tickets/{ticket_id}/asignacion", {"agente_id": "2"}).status_code, 302)
        self.sign_in(2)
        for state in ("EN_PROCESO", "RESUELTO", "CERRADO"):
            response = self.post(f"/tickets/{ticket_id}/estado", {"estado": state})
            self.assertEqual(response.status_code, 302)
        with self.db.connect().raw as conn:
            events = conn.execute("SELECT tipo FROM ticket_actividad ORDER BY id").fetchall()
            self.assertEqual([row[0] for row in events], ["CREADO", "ASIGNADO", "ESTADO", "ESTADO", "ESTADO"])
        response = self.post(f"/tickets/{ticket_id}/comentarios", {"contenido": "Cerrado"})
        self.assertEqual(response.status_code, 400)

    def test_two_browser_sessions_do_not_share_identity(self):
        ticket_id = self.create_ticket()
        other = self.app.test_client()
        self.sign_in(4, other)
        self.assertEqual(other.get(f"/tickets/{ticket_id}").status_code, 403)
        self.assertEqual(self.client.get(f"/tickets/{ticket_id}").status_code, 200)

    def test_publisher_cannot_manage_users(self):
        self.sign_in()
        self.assertEqual(self.client.get("/usuarios").status_code, 403)
        self.assertEqual(self.post("/usuarios/2/rol", {"role": "SUPERVISOR"}).status_code, 403)

    def test_supervisor_can_view_team_and_change_role(self):
        self.sign_in(3)
        self.assertEqual(self.client.get("/usuarios").status_code, 200)
        self.assertEqual(self.post("/usuarios/4/rol", {"role": "AGENTE"}).status_code, 302)
        with self.db.connect().raw as conn:
            self.assertEqual(conn.execute("SELECT id_rol FROM usuarios WHERE id=4").fetchone()[0], 2)

    def test_publisher_cannot_forge_status_change(self):
        ticket_id = self.create_ticket()
        response = self.post(f"/tickets/{ticket_id}/estado", {"estado": "EN_PROCESO"})
        self.assertEqual(response.status_code, 400)
        with self.db.connect().raw as conn:
            self.assertEqual(conn.execute("SELECT estado FROM tickets WHERE id=?", (ticket_id,)).fetchone()[0], "ABIERTO")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ticket_actividad").fetchone()[0], 1)

    def test_logout_requires_post_and_clears_session(self):
        self.sign_in()
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.post("/logout").status_code, 302)
        self.assertEqual(self.client.get("/tickets").status_code, 302)

    def test_history_failure_rolls_back_new_ticket(self):
        self.sign_in()
        with self.db.connect().raw as conn:
            conn.execute("DROP TABLE ticket_actividad")
        response = self.post("/tickets/nuevo", {"titulo": "Prueba", "descripcion": "Detalle"})
        self.assertEqual(response.status_code, 503)
        with self.db.connect().raw as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
