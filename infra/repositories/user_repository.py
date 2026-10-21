"""Consultas de usuarios; participa en la transacción del servicio."""

USER_COLUMNS = "u.id, u.username, u.email, u.password_hash, r.nombre AS role"
USER_JOIN = "FROM usuarios u JOIN roles r ON r.id = u.id_rol"


class UserRepository:
    def __init__(self, cursor):
        self.cursor = cursor

    def buscar_por_username(self, username):
        self.cursor.execute(
            f"SELECT {USER_COLUMNS} {USER_JOIN} WHERE u.username=%s", (username,))
        return self.cursor.fetchone()

    def buscar_por_id(self, user_id):
        self.cursor.execute(
            f"SELECT {USER_COLUMNS} {USER_JOIN} WHERE u.id=%s", (user_id,))
        return self.cursor.fetchone()

    def crear(self, username, email, password_hash, role):
        self.cursor.execute("SELECT id FROM roles WHERE nombre=%s", (role,))
        row = self.cursor.fetchone()
        if row is None:
            raise ValueError("Rol inexistente. Importe el esquema de base de datos.")
        self.cursor.execute(
            "SELECT id FROM usuarios WHERE username=%s OR email=%s", (username, email))
        if self.cursor.fetchone():
            raise ValueError("El usuario o email ya existe.")
        self.cursor.execute(
            "INSERT INTO usuarios (username, email, password_hash, id_rol) VALUES (%s, %s, %s, %s)",
            (username, email, password_hash, row["id"]))
        return self.cursor.lastrowid
