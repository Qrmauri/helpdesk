"""Vista temporal para revisión visual: python tests/preview_web.py.

Usa exclusivamente la base de pruebas en memoria. No conecta con MySQL.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_fixture import TestDatabase
from services.auth_service import AuthService
import services.auth_service as auth_module
import services.ticket_service as ticket_module
from web import create_app


def main():
    from waitress import serve

    db = TestDatabase(AuthService.hash_password("Prueba-segura123"))
    auth_module.get_connection = db.connect
    ticket_module.get_connection = db.connect
    with db.connect().raw as conn:
        conn.executemany(
            "INSERT INTO tickets (id,titulo,descripcion,estado,id_usuario,asignado_a,creado_en) VALUES (?,?,?,?,?,?,?)", [
                (1, "Sin acceso a la carpeta compartida", "No puedo abrir los archivos del equipo de Finanzas. Aparece el mensaje: acceso denegado.", "EN_PROCESO", 1, 2, "2026-10-19 09:15:00"),
                (2, "Configurar correo en equipo nuevo", "Necesito configurar mi cuenta corporativa en el computador de recepción.", "ABIERTO", 1, None, "2026-10-20 09:40:00"),
                (3, "Impresora de recepción sin conexión", "La impresora no aparece en la red. Ya revisamos los cables y reiniciamos el equipo.", "EN_ESPERA", 4, 2, "2026-10-21 09:20:00"),
                (4, "Actualización de software contable", "Solicitamos instalar la versión aprobada por el área de Contabilidad.", "RESUELTO", 1, 2, "2026-10-21 11:30:00"),
                (5, "Conexión intermitente en sala de reuniones", "La conexión se corta durante las videollamadas en la sala del segundo piso.", "ABIERTO", 4, None, "2026-10-22 08:45:00"),
                (6, "Restablecer acceso a intranet", "Recuperar acceso a las herramientas internas de la empresa.", "CERRADO", 1, 2, "2026-10-22 09:00:00"),
            ])
        conn.executemany(
            "INSERT INTO ticket_actividad (ticket_id,usuario_id,tipo,contenido,creado_en) VALUES (?,?,?,?,?)", [
                (1, 1, "CREADO", "Ticket creado.", "2026-10-19 09:15:00"),
                (1, 3, "ASIGNADO", "Ticket asignado al agente #2.", "2026-10-22 09:20:00"),
                (1, 2, "ESTADO", "Estado: ABIERTO → EN_PROCESO.", "2026-10-22 09:25:00"),
                (1, 2, "COMENTARIO", "Hola, estoy revisando los permisos de la carpeta. ¿Puedes confirmar si el problema también ocurre desde otro equipo?", "2026-10-22 09:30:00"),
                (1, 1, "COMENTARIO", "Sí, lo probé desde el equipo de recepción y aparece el mismo mensaje. El resto de las carpetas funciona bien.", "2026-10-22 09:35:00"),
            ])
        conn.execute("UPDATE tickets SET actualizado_en='2026-10-22 09:25:00' WHERE id=1")
    print("Vista de prueba: http://127.0.0.1:8001", flush=True)
    print("Usuarios: supervisor / agente / publicador. Clave de prueba: Prueba-segura123", flush=True)
    try:
        serve(create_app({"PREVIEW_MODE": True}), host="127.0.0.1", port=8001, threads=1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
