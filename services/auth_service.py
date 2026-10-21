import hashlib
import hmac
import re
import secrets

import pymysql

from infra.db import get_connection, transaction
from infra.repositories.user_repository import UserRepository
from src.domain.usuario import Usuario


class AuthService:
    """Autenticación y gestión de roles; los errores se propagan a la interfaz."""

    def __init__(self):
        self.usuario_actual = None

    @staticmethod
    def hash_password(password):
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                n=131072, r=8, p=1, maxmem=256 * 1024 * 1024)
        return f"scrypt${salt.hex()}${digest.hex()}"

    @staticmethod
    def verificar_password(password, stored):
        if not isinstance(stored, str):
            return False
        # Compatibilidad temporal: el login migra SHA-256 después de verificarlo.
        if re.fullmatch(r"[0-9a-fA-F]{64}", stored):
            return hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).hexdigest(), stored.lower())
        try:
            algorithm, salt_hex, digest_hex = stored.split("$")
            if algorithm != "scrypt" or len(salt_hex) != 32 or len(digest_hex) != 128:
                return False
            digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                    n=131072, r=8, p=1, maxmem=256 * 1024 * 1024)
            return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
        except ValueError:
            return False

    def registrar(self, username, email, password, role=Usuario.PUBLICADOR):
        if role != Usuario.PUBLICADOR:
            raise ValueError("El registro público solo permite el rol PUBLICADOR.")
        username, email = username.strip(), email.strip().lower()
        if not re.fullmatch(r"[\w.-]{3,50}", username):
            raise ValueError("El usuario debe tener entre 3 y 50 letras, números, puntos, guiones o guiones bajos.")
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Ingrese un email válido (máximo 254 caracteres).")
        if not password.strip() or not 10 <= len(password) <= 128:
            raise ValueError("La contraseña debe tener entre 10 y 128 caracteres y no contener solo espacios.")
        password_hash = self.hash_password(password)
        with transaction(get_connection) as cursor:
            try:
                user_id = UserRepository(cursor).crear(username, email, password_hash, role)
            except pymysql.IntegrityError as exc:
                if exc.args and exc.args[0] == 1062:
                    raise ValueError("El usuario o email ya existe.") from None
                raise
        return user_id

    def login(self, username, password):
        self.usuario_actual = None
        if not username.strip() or not password or len(username.strip()) > 50 or len(password) > 128:
            raise ValueError("Credenciales inválidas.")
        with transaction(get_connection) as cursor:
            row = UserRepository(cursor).buscar_por_username(username.strip())
            if row is None or not self.verificar_password(password, row["password_hash"]):
                raise ValueError("Credenciales inválidas.")
            usuario = Usuario(**row)
            if not row["password_hash"].startswith("scrypt$"):
                cursor.execute("UPDATE usuarios SET password_hash=%s WHERE id=%s",
                               (self.hash_password(password), usuario.id))
        self.usuario_actual = usuario
        return usuario

    def listar_usuarios(self, offset=0):
        self._exigir_supervisor()
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Página inválida.")
        with transaction(get_connection) as cursor:
            cursor.execute("SELECT u.id, u.username, r.nombre AS role "
                           "FROM usuarios u JOIN roles r ON r.id=u.id_rol ORDER BY u.id LIMIT 50 OFFSET %s", (offset,))
            return cursor.fetchall()

    def obtener_usuario_actual(self):
        """Actualiza los permisos para no conservar un rol revocado en otra instancia."""
        if self.usuario_actual is None:
            raise ValueError("Debe iniciar sesión.")
        with transaction(get_connection) as cursor:
            row = UserRepository(cursor).buscar_por_id(self.usuario_actual.id)
        if row is None:
            self.usuario_actual = None
            raise ValueError("La cuenta ya no existe. Inicie sesión nuevamente.")
        self.usuario_actual = Usuario(**row)
        return self.usuario_actual

    def cambiar_rol(self, user_id, role):
        self._exigir_supervisor()
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise ValueError("ID de usuario inválido.")
        if role not in (Usuario.PUBLICADOR, Usuario.AGENTE, Usuario.SUPERVISOR):
            raise ValueError("Rol inválido.")
        if user_id == self.usuario_actual.id:
            raise ValueError("No puede cambiar su propio rol durante la sesión.")
        with transaction(get_connection) as cursor:
            cursor.execute("SELECT id FROM roles WHERE nombre=%s", (role,))
            target = cursor.fetchone()
            if target is None:
                raise ValueError("Rol inexistente.")
            cursor.execute("SELECT id FROM usuarios WHERE id=%s FOR UPDATE", (user_id,))
            if cursor.fetchone() is None:
                raise ValueError("Usuario inexistente.")
            if role != Usuario.AGENTE:
                cursor.execute("SELECT id FROM tickets WHERE asignado_a=%s AND estado <> 'CERRADO' LIMIT 1", (user_id,))
                if cursor.fetchone():
                    raise ValueError("Reasigne los tickets activos de este agente antes de cambiar su rol.")
            cursor.execute("UPDATE usuarios SET id_rol=%s WHERE id=%s", (target["id"], user_id))

    def _exigir_supervisor(self):
        if self.usuario_actual is None or not self.usuario_actual.es_supervisor():
            raise ValueError("Solo un supervisor puede gestionar usuarios.")
        if not self.obtener_usuario_actual().es_supervisor():
            raise ValueError("Su cuenta ya no tiene permisos de supervisor.")

    def logout(self):
        self.usuario_actual = None
