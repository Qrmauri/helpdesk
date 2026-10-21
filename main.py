from infra import db
from services.auth_service import AuthService
from services.ticket_service import TicketService
from src.domain.errors import ErrorPersistencia
from ui.menu import Menu


def main():
    try:
        db.initialize()
    except (ValueError, ErrorPersistencia) as exc:
        print(f"No se pudo iniciar Helpdesk: {exc}")
        return 1
    auth = AuthService()
    Menu(auth, TicketService(auth)).mostrar_menu_principal()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
