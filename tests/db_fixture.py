"""Adaptador SQLite exclusivo de pruebas: ejecuta las consultas, no simula servicios.

Traduce marcadores y FOR UPDATE. No prueba los bloqueos ni el DDL de MySQL.
"""
import sqlite3
import uuid
from datetime import datetime

import pymysql


class Cursor:
    def __init__(self, connection):
        self.raw = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.raw.close()

    def execute(self, sql, params=()):
        sql = sql.replace("%s", "?").replace(" FOR UPDATE", "")
        params = tuple(value.isoformat(sep=" ") if isinstance(value, datetime) else value for value in params)
        try:
            return self.raw.execute(sql, params)
        except sqlite3.IntegrityError as exc:
            raise pymysql.IntegrityError(1062, str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise pymysql.ProgrammingError(1146, str(exc)) from exc

    def fetchone(self):
        row = self.raw.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.raw.fetchall()]

    @property
    def lastrowid(self):
        return self.raw.lastrowid

    @property
    def rowcount(self):
        return self.raw.rowcount


class Connection:
    def __init__(self, path):
        self.raw = sqlite3.connect(path, uri=True, check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys=ON")

    def cursor(self):
        return Cursor(self.raw)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


class TestDatabase:
    def __init__(self, password_hash):
        self.path = f"file:helpdesk-tests-{uuid.uuid4().hex}?mode=memory&cache=shared"
        self.connections = []
        self.keeper = sqlite3.connect(self.path, uri=True)
        with self.keeper as conn:
            conn.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE roles (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE);
                INSERT INTO roles VALUES (1, 'PUBLICADOR'), (2, 'AGENTE'), (3, 'SUPERVISOR');
                CREATE TABLE usuarios (
                    id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE,
                    password_hash TEXT, id_rol INTEGER REFERENCES roles(id));
                CREATE TABLE tickets (
                    id INTEGER PRIMARY KEY, titulo TEXT, descripcion TEXT, estado TEXT,
                    id_usuario INTEGER REFERENCES usuarios(id), asignado_a INTEGER REFERENCES usuarios(id),
                    creado_en TEXT DEFAULT CURRENT_TIMESTAMP, actualizado_en TEXT);
                CREATE TABLE ticket_actividad (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER REFERENCES tickets(id),
                    usuario_id INTEGER REFERENCES usuarios(id), tipo TEXT, contenido TEXT,
                    creado_en TEXT DEFAULT CURRENT_TIMESTAMP);
            """)
            conn.executemany("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?)", [
                (1, "publicador", "p@example.com", password_hash, 1),
                (2, "agente", "a@example.com", password_hash, 2),
                (3, "supervisor", "s@example.com", password_hash, 3),
                (4, "otro", "o@example.com", password_hash, 1),
            ])

    def connect(self):
        conn = Connection(self.path)
        self.connections.append(conn)
        return conn

    def close(self):
        for conn in self.connections:
            conn.close()
        self.keeper.close()
