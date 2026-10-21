"""Conexiones y transacciones MySQL sin credenciales predeterminadas."""
import logging
import os
from contextlib import contextmanager

import pymysql

from src.domain.errors import ErrorPersistencia


def get_connection():
    user = os.environ.get("HELPDESK_DB_USER")
    password = os.environ.get("HELPDESK_DB_PASSWORD")
    if not user or not password:
        raise ValueError("Configure HELPDESK_DB_USER y HELPDESK_DB_PASSWORD.")
    try:
        port = int(os.environ.get("HELPDESK_DB_PORT", "3306"))
    except ValueError:
        raise ValueError("HELPDESK_DB_PORT debe ser un número.") from None
    if not 1 <= port <= 65535:
        raise ValueError("HELPDESK_DB_PORT debe estar entre 1 y 65535.")
    try:
        return pymysql.connect(
            host=os.environ.get("HELPDESK_DB_HOST", "localhost"), port=port,
            user=user, password=password,
            database=os.environ.get("HELPDESK_DB_NAME", "helpdesk"),
            charset="utf8mb4", autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5, read_timeout=10, write_timeout=10,
        )
    except pymysql.MySQLError as exc:
        logging.getLogger(__name__).error("Conexión MySQL fallida (%s).", type(exc).__name__)
        raise ErrorPersistencia("No se pudo conectar a MySQL. Revise la configuración y el servidor.") from exc


@contextmanager
def transaction(connection_factory=get_connection):
    conn = connection_factory()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except pymysql.MySQLError:
            logging.getLogger(__name__).error("No se pudo revertir la transacción MySQL.")
            raise ErrorPersistencia("Se perdió la conexión durante la operación. Revise su resultado antes de reintentar.") from exc
        if isinstance(exc, pymysql.MySQLError):
            logging.getLogger(__name__).error("Operación MySQL fallida (%s).", type(exc).__name__)
            raise ErrorPersistencia("No se pudo completar la operación en la base de datos.") from exc
        raise
    finally:
        conn.close()


def initialize():
    """Comprueba la conexión; no crea ni modifica el esquema."""
    conn = get_connection()
    conn.close()
