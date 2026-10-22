"""Interfaz web local para Helpdesk. Ejecutar con python web.py."""
import hmac
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

from services.auth_service import AuthService
from services.ticket_service import TicketService
from src.domain.errors import AccesoDenegado, ErrorPersistencia
from src.domain.ticket import Ticket


def create_app(config=None):
    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("HELPDESK_WEB_SECRET") or secrets.token_hex(32),
        SESSION_COOKIE_NAME="helpdesk_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("HELPDESK_WEB_HTTPS") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=64 * 1024,
        MAX_FORM_MEMORY_SIZE=64 * 1024,
        MAX_FORM_PARTS=20,
    )
    if config:
        app.config.update(config)
    if len(app.config["SECRET_KEY"]) < 32:
        raise ValueError("HELPDESK_WEB_SECRET debe tener al menos 32 caracteres.")
    limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])
    app.extensions["helpdesk_limiter"] = limiter

    @app.before_request
    def prepare_request():
        if request.endpoint == "static":
            return
        g.auth = AuthService()
        g.tickets = TicketService(g.auth)
        g.usuario = None
        if request.method == "POST":
            expected = session.get("csrf_token", "")
            supplied = request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
                abort(400, "El formulario venció. Recargue la página e intente nuevamente.")
        user_id = session.get("user_id")
        if user_id is not None:
            try:
                g.usuario = g.auth.restaurar_sesion(user_id)
            except ValueError:
                session.clear()

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; img-src 'self'; script-src 'none'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.template_global()
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    @app.context_processor
    def template_context():
        return dict(current_user=getattr(g, "usuario", None), estados=Ticket.ESTADOS_VALIDOS)

    @app.template_filter("fecha")
    def format_date(value, short=False):
        if not value:
            return "Sin cambios"
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime("%d/%m/%Y" if short else "%d/%m/%Y · %H:%M")

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.usuario is None:
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def require_supervisor():
        if not g.usuario.es_supervisor():
            abort(403, "Esta sección está disponible para supervisores.")

    def page_number():
        try:
            page = int(request.args.get("pagina", "1"))
        except ValueError:
            abort(400, "Página inválida.")
        if not 1 <= page <= 1000000:
            abort(400, "Página inválida.")
        return page

    @app.get("/")
    def index():
        return redirect(url_for("tickets" if g.usuario else "login"))

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("10 per minute", methods=["POST"])
    def login():
        if request.method == "POST":
            session.clear()
            g.usuario = None
            try:
                usuario = g.auth.login(request.form.get("username", ""), request.form.get("password", ""))
            except ValueError as exc:
                return render_template("auth.html", register=False, error=str(exc)), 400
            session["user_id"] = usuario.id
            session["csrf_token"] = secrets.token_hex(32)
            session.permanent = True
            return redirect(url_for("tickets"))
        if g.usuario:
            return redirect(url_for("tickets"))
        return render_template("auth.html", register=False)

    @app.route("/registro", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"])
    def register():
        if request.method == "POST":
            try:
                g.auth.registrar(request.form.get("username", ""), request.form.get("email", ""),
                                 request.form.get("password", ""))
            except ValueError as exc:
                return render_template("auth.html", register=True, error=str(exc)), 400
            flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
        return render_template("auth.html", register=True)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/tickets")
    @authenticated
    def tickets():
        page = page_number()
        all_tickets = request.args.get("alcance") == "todos"
        if all_tickets:
            require_supervisor()
        rows = (g.tickets.listar_todos if all_tickets else g.tickets.listar_mis_tickets)(offset=(page - 1) * 50)
        return render_template("tickets.html", tickets=rows, page=page, all_tickets=all_tickets,
                               has_next=len(rows) == 50)

    @app.route("/tickets/nuevo", methods=["GET", "POST"])
    @authenticated
    def new_ticket():
        if request.method == "POST":
            try:
                ticket_id = g.tickets.crear_ticket(request.form.get("titulo", ""), request.form.get("descripcion", ""))
            except ValueError as exc:
                return render_template("new_ticket.html", error=str(exc)), 400
            flash("Ticket creado. Puedes seguir la conversación desde aquí.", "success")
            return redirect(url_for("ticket_detail", ticket_id=ticket_id))
        return render_template("new_ticket.html")

    @app.get("/tickets/<int:ticket_id>")
    @authenticated
    def ticket_detail(ticket_id):
        page = page_number()
        ticket = g.tickets.obtener_ticket(ticket_id)
        activity = g.tickets.listar_actividad(ticket_id, offset=(page - 1) * 50)
        can_change = g.usuario.es_supervisor() or (g.usuario.es_agente() and g.usuario.id == ticket.asignado_a)
        if ticket.esta_cerrado() and not g.usuario.es_supervisor():
            can_change = False
        return render_template("ticket_detail.html", ticket=ticket, activity=activity, page=page,
                               has_next=len(activity) == 50, can_change=can_change,
                               transitions=Ticket.TRANSICIONES[ticket.estado])

    @app.post("/tickets/<int:ticket_id>/comentarios")
    @authenticated
    def add_comment(ticket_id):
        g.tickets.agregar_comentario(ticket_id, request.form.get("contenido", ""))
        flash("Comentario publicado.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id) + "#actividad")

    @app.post("/tickets/<int:ticket_id>/estado")
    @authenticated
    def change_status(ticket_id):
        g.tickets.cambiar_estado(ticket_id, request.form.get("estado", ""))
        flash("Estado actualizado y registrado en el historial.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    @app.post("/tickets/<int:ticket_id>/asignacion")
    @authenticated
    def assign_ticket(ticket_id):
        require_supervisor()
        try:
            agente_id = int(request.form.get("agente_id", "0"))
        except ValueError:
            raise ValueError("El ID del agente debe ser un número entero positivo.") from None
        g.tickets.asignar_ticket(ticket_id, agente_id)
        flash("Asignación actualizada y registrada en el historial.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    @app.get("/usuarios")
    @authenticated
    def users():
        require_supervisor()
        page = page_number()
        rows = g.auth.listar_usuarios(offset=(page - 1) * 50)
        return render_template("users.html", users=rows, page=page, has_next=len(rows) == 50)

    @app.post("/usuarios/<int:user_id>/rol")
    @authenticated
    def change_role(user_id):
        require_supervisor()
        g.auth.cambiar_rol(user_id, request.form.get("role", ""))
        flash("Rol actualizado.", "success")
        return redirect(url_for("users"))

    @app.errorhandler(AccesoDenegado)
    def forbidden(exc):
        return render_template("error.html", code=403, message=str(exc)), 403

    @app.errorhandler(ValueError)
    def validation_error(exc):
        return render_template("error.html", code=400, message=str(exc)), 400

    @app.errorhandler(ErrorPersistencia)
    def database_error(exc):
        return render_template("error.html", code=503, message=str(exc)), 503

    @app.errorhandler(HTTPException)
    def http_error(exc):
        messages = {
            404: "No encontramos esa página.", 405: "Esta acción no está disponible por ese método.",
            413: "El formulario es demasiado grande.", 429: "Demasiados intentos. Espera un minuto y vuelve a intentar.",
        }
        return render_template("error.html", code=exc.code,
                               message=messages.get(exc.code, exc.description)), exc.code

    return app


if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("HELPDESK_WEB_PORT", "8000"))
    print(f"Helpdesk web: http://127.0.0.1:{port}", flush=True)
    serve(create_app(), host="127.0.0.1", port=port, threads=4)
