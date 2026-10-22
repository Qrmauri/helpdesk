# Helpdesk — SurSoporte Ltda.

Sistema de soporte técnico con interfaz web y consola, escrito en Python y respaldado por MySQL. Permite registrar usuarios, iniciar sesión, crear y asignar tickets, gestionar estados y conversar con el equipo mediante comentarios e historial por ticket.

## Requisitos

- Python 3.11 o posterior con soporte OpenSSL para `hashlib.scrypt`.
- MySQL 8.0.16 o posterior, con tablas InnoDB.
- Un cliente MySQL para importar el esquema (terminal o MySQL Workbench).

## Instalación en Windows / PowerShell

Desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Los comandos usan el intérprete del entorno directamente; no es necesario activar scripts de PowerShell. `requirements.txt` fija las dependencias, incluido el soporte RSA que PyMySQL necesita para ciertos métodos de autenticación de MySQL.

## Base de datos nueva

Conéctate como administrador de MySQL e importa `sql/schema.sql`. En el cliente interactivo, desde la raíz del proyecto:

```sql
SOURCE sql/schema.sql;
```

El script crea la base `helpdesk`, las tablas `roles`, `usuarios`, `tickets` y `ticket_actividad`, los tres roles, índices y restricciones. No crea usuarios de la aplicación ni incluye contraseñas predeterminadas. Úsalo solo para una instalación nueva: fallará si las tablas ya existen.

Crea una cuenta MySQL dedicada. Sustituye el texto de ejemplo por una contraseña propia antes de ejecutarlo:

```sql
CREATE USER 'helpdesk_app'@'localhost' IDENTIFIED BY 'REEMPLAZAR_POR_UN_SECRETO_LOCAL';
GRANT SELECT, INSERT, UPDATE ON helpdesk.* TO 'helpdesk_app'@'localhost';
```

La cuenta de ejecución no necesita `root`, creación de tablas ni permisos de borrado. Si MySQL está en otra máquina, ajusta el host de la cuenta y configura una conexión protegida en tu infraestructura; esta configuración está pensada para ejecución local.

## Configuración y ejecución

La aplicación lee variables de entorno. `.env.example` sirve como referencia y **no se carga automáticamente**.

```powershell
$env:HELPDESK_DB_HOST = 'localhost'
$env:HELPDESK_DB_PORT = '3306'
$env:HELPDESK_DB_NAME = 'helpdesk'
$env:HELPDESK_DB_USER = 'helpdesk_app'
$credencial = Get-Credential -UserName 'helpdesk_app' -Message 'Contraseña de la cuenta MySQL'
$env:HELPDESK_DB_PASSWORD = $credencial.GetNetworkCredential().Password
.\.venv\Scripts\python.exe main.py
Remove-Item Env:HELPDESK_DB_PASSWORD
```

`HELPDESK_DB_USER` y `HELPDESK_DB_PASSWORD` son obligatorias. El resto usa los valores mostrados como predeterminados. Si la conexión falla, el programa termina con un mensaje y código de salida 1. El arranque comprueba la conexión, pero no aplica migraciones ni crea tablas.

Las contraseñas de usuarios se solicitan con `getpass`, sin mostrarlas en pantalla. Ejecuta el programa desde una terminal interactiva.

## Interfaz web

Después de instalar las dependencias, configurar MySQL y aplicar el esquema o las migraciones:

```powershell
# Opcional: conservar esta variable entre arranques evita invalidar las sesiones.
$env:HELPDESK_WEB_SECRET = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
.\.venv\Scripts\python.exe web.py
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000). La web y la consola utilizan las mismas cuentas, permisos y base MySQL. Puedes seguir usando `main.py` para la consola.

La web incluye:

- Registro como publicador e inicio y cierre de sesión.
- Bandeja de tickets propios/asignados y vista global para supervisores.
- Creación y detalle de tickets con conversación e historial.
- Cambios de estado para el agente asignado o un supervisor.
- Asignación de responsables, listado de usuarios y gestión de roles para supervisores.
- Diseño adaptable para escritorio y móvil, formularios con etiquetas y navegación por teclado.

Waitress sirve la aplicación únicamente en `127.0.0.1`; no se publica en Internet. `HELPDESK_WEB_PORT` permite cambiar el puerto. Si no defines `HELPDESK_WEB_SECRET`, se genera una clave aleatoria al arrancar y las sesiones anteriores dejan de ser válidas al reiniciar. Nunca compartas esa clave.

Las sesiones firmadas guardan el ID, el token de formulario y metadatos de sesión, sin contraseñas ni roles. Los permisos se consultan de nuevo desde la base. La sesión caduca tras ocho horas de inactividad y las cookies son `HttpOnly` y `SameSite=Lax`. Los formularios requieren protección CSRF, los textos se escapan antes de mostrarlos y las páginas privadas no se almacenan en caché.

Hay límites de diez envíos de login y cinco registros por minuto y dirección IP. El contador vive en memoria del proceso y se reinicia con el servidor; para un despliegue con varias instancias debe reemplazarse por almacenamiento compartido y configurarse correctamente el proxy. Para servir detrás de HTTPS, configura `HELPDESK_WEB_HTTPS=1` para activar cookies `Secure` y HSTS. Esta entrega está preparada para uso local; la configuración de hosting público no forma parte de ella.

### Vista de prueba sin MySQL

Para explorar las pantallas sin tocar datos reales:

```powershell
.\.venv\Scripts\python.exe tests/preview_web.py
```

Abre [http://127.0.0.1:8001](http://127.0.0.1:8001). Usuarios de ejemplo: `supervisor`, `agente` y `publicador`; contraseña exclusiva de prueba: `Prueba-segura123`. La página muestra una advertencia de vista de prueba. Los cambios viven en memoria y se pierden al detener el proceso. Es un auxiliar de pruebas, separado del arranque real `web.py`.

## Primer supervisor

1. Ejecuta el programa y registra tu usuario; recibirá el rol `PUBLICADOR`.
2. Sal del programa.
3. Desde una conexión administrativa a MySQL, promueve únicamente la cuenta autorizada. Sustituye `tu_usuario`:

```sql
USE helpdesk;
UPDATE usuarios u
JOIN roles r ON r.nombre = 'SUPERVISOR'
SET u.id_rol = r.id
WHERE u.username = 'tu_usuario';

SELECT u.id, u.username, r.nombre AS rol
FROM usuarios u JOIN roles r ON r.id = u.id_rol
WHERE u.username = 'tu_usuario';
```

4. Vuelve a iniciar sesión. Desde `Ver usuarios` y `Cambiar rol de usuario` podrás habilitar agentes u otros supervisores.

El registro público no permite elegir roles privilegiados. Un supervisor no puede cambiar su propio rol durante la sesión. Antes de quitar el rol de agente a un usuario, debe reasignar sus tickets activos. Los servicios consultan el rol vigente antes de operar para detectar cambios hechos desde otra instancia. Para actualizar las opciones visibles del menú, vuelve a iniciar sesión.

## Permisos y funcionamiento

| Operación | Publicador | Agente | Supervisor |
|---|---|---|---|
| Crear ticket | Sí | Sí | Sí |
| Ver tickets propios o asignados | Sí | Sí | Sí |
| Ver todos los tickets | No | No | Sí |
| Asignar tickets a agentes | No | No | Sí |
| Cambiar estado | No | Solo los asignados | Sí |
| Reabrir un ticket cerrado | No | No | Sí |
| Consultar conversación e historial | Autor del ticket | Autor o agente asignado | Sí |
| Comentar tickets abiertos | Autor del ticket | Autor o agente asignado | Sí |
| Ver usuarios y gestionar roles | No | No | Sí |

La identidad del autor se obtiene de la sesión, no de un ID ingresado por el usuario. Las listas de tickets y usuarios se muestran en páginas de 50; escribe `N` para avanzar.

Transiciones admitidas:

```text
ABIERTO → EN_PROCESO
EN_PROCESO → EN_ESPERA o RESUELTO
EN_ESPERA → EN_PROCESO o RESUELTO
RESUELTO → CERRADO o EN_PROCESO
CERRADO → EN_PROCESO (solo supervisor)
```

Los tickets cerrados no se pueden asignar. El destino de una asignación debe existir y tener el rol `AGENTE`. Las asignaciones y los cambios de estado bloquean las filas durante la transacción para evitar actualizaciones simultáneas incompatibles.

Se validan usuarios de 3 a 50 caracteres, emails de hasta 254, contraseñas nuevas de 10 a 128, títulos de 1 a 200 y descripciones de 1 a 10000. El formato de correo se comprueba de forma básica; no se verifica la propiedad de la dirección. No hay adjuntos ni recuperación de contraseñas en esta versión.

## Conversación e historial

Cada ticket tiene una actividad paginada, con las entradas más recientes primero. Se registra quién creó el caso, quién lo asignó, los cambios de estado (estado anterior y nuevo) y los comentarios con su autor y fecha.

La creación/asignación/cambio de estado y su entrada de historial se guardan en la misma transacción: si no se puede guardar el historial, se revierte también la operación. Las fechas de persistencia se obtienen del reloj de la base y se muestran tal como están almacenadas.

El autor, el agente asignado y los supervisores pueden consultar la conversación. Pueden añadir comentarios de 1 a 5000 caracteres mientras el ticket no esté cerrado. El historial permanece consultable al cerrar el caso; no hay funciones para editar o borrar entradas. En consola están disponibles las opciones `8. Ver detalle e historial` y `9. Añadir comentario`.

## Actualizar una base existente

No ejecutes `schema.sql` sobre datos existentes. Realiza un respaldo y revisa primero:

```sql
SHOW CREATE TABLE helpdesk.roles;
SHOW CREATE TABLE helpdesk.usuarios;
SHOW CREATE TABLE helpdesk.tickets;
```

La aplicación espera `usuarios.id_rol` relacionado con `roles.id`, `roles.nombre` y `tickets.id_usuario`. Este último se mapea al atributo de dominio `creado_por`; no hace falta renombrar la columna.

Revisa `sql/migrations/001_passwords_y_actualizacion.sql`: amplía `password_hash` a 255 caracteres y añade `tickets.actualizado_en`. Si esa columna ya existe, omite esa sentencia. Ajusta el nombre de base si no utilizas `helpdesk`. MySQL realiza commits implícitos en estas operaciones: el respaldo es necesario para volver atrás.

Compara además tu esquema con el nuevo: deben existir claves únicas para `username` y `email`, claves foráneas para roles/autores/asignaciones, valores predeterminados para `creado_en` y los índices de autor y agente. El script de migración no añade automáticamente estas restricciones porque puede haber diferencias o duplicados que requieran revisión. Corrige esos datos antes de añadir restricciones.

Las contraseñas SHA-256 previas siguen siendo aceptadas y se reemplazan por scrypt con salt aleatorio después de un login correcto. La actualización del hash debe poder confirmarse en MySQL antes de abrir la sesión. Las contraseñas antiguas no tienen que cumplir la nueva longitud mínima para iniciar sesión, pero el límite máximo sigue siendo 128 caracteres. La ampliación de la columna debe hacerse antes de ejecutar el código nuevo.

La contraseña de MySQL que antes estaba en el código debe cambiarse desde la administración del servidor. Quitarla del archivo no revoca ese secreto ni lo elimina de copias o historiales anteriores.

### Migración de comentarios e historial

Si ya aplicaste la migración 001, importa una sola vez `sql/migrations/002_comentarios_historial.sql` con una conexión administrativa y un respaldo previo. Desde el cliente MySQL, en la raíz del proyecto:

```sql
SOURCE sql/migrations/002_comentarios_historial.sql;
```

Esta migración añade `ticket_actividad` y sus claves foráneas sin modificar tickets previos. El historial de esos tickets empieza cuando se instala esta función; no se inventan acciones históricas. Si tu base no se llama `helpdesk`, ajusta el `USE` del script. Si `usuarios.id` o `tickets.id` tienen otro tipo (por ejemplo `INT UNSIGNED`), adapta las columnas relacionadas de la nueva tabla para que coincidan antes de importarla.

La tabla de actividad es necesaria tanto para la consola como para la web nuevas. Si falta, las escrituras que requieren historial fallarán y se revertirán. No necesitas ejecutar la migración 002 en una base creada con el `schema.sql` actualizado, que ya la incluye.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Las pruebas usan `unittest`. Las regresiones de servicios utilizan conexiones simuladas. Las pruebas web ejecutan los servicios reales contra una base SQLite temporal en memoria mediante un adaptador exclusivo de pruebas: verifican registro, sesiones independientes, creación, asignación, estados, comentarios, permisos, CSRF, escape de HTML e historial atómico. No requieren un servidor ni modifican una base real. El adaptador traduce marcadores SQL y omite `FOR UPDATE`, por lo que no prueba bloqueos, concurrencia ni el DDL de MySQL; sigue siendo necesaria una prueba de integración con el servidor real.

Para comprobar la instalación en una base de prueba:

1. Importa el esquema y configura las variables de entorno.
2. Registra un publicador, un futuro agente y el futuro supervisor; comprueba que no se aceptan duplicados ni datos inválidos.
3. Promueve al supervisor desde MySQL y al agente desde su menú.
4. Crea un ticket como publicador, asígnalo como supervisor y recorre sus estados como agente.
5. Comprueba que un agente ajeno no puede modificarlo, que el cerrado no se puede asignar y que solo un supervisor puede reabrirlo.
6. Detén el servidor de prueba y confirma que aparece un error sin anunciar éxito ni mostrar detalles internos SQL.
7. Publica comentarios con el solicitante y el agente, confirma sus autores en el historial e intenta acceder con un usuario ajeno al ticket.
8. Inicia `web.py` y repite el recorrido desde el navegador. Comprueba que el cierre de sesión devuelve a la pantalla de acceso.

## Estructura

```text
main.py                         Arranque y composición de servicios
web.py                          Aplicación web Flask y servidor local Waitress
ui/menu.py                      Entradas y mensajes de consola
ui/templates/                   Páginas HTML con escape automático
ui/static/                      Estilos adaptables e icono
services/auth_service.py         Autenticación, contraseñas y roles
services/ticket_service.py       Casos de uso de tickets
src/domain/                     Usuario, Ticket, reglas y errores
infra/db.py                     Conexiones y transacciones
infra/repositories/              Consultas de usuarios
sql/schema.sql                  Esquema para instalaciones nuevas
sql/migrations/                 Cambios revisables para bases previas
tests/test_regressions.py        Pruebas automatizadas
tests/test_activity.py           Comentarios, acceso e historial
tests/test_web.py                Recorridos HTTP e integración de servicios
tests/db_fixture.py              Adaptador SQL exclusivo de pruebas
tests/preview_web.py             Vista temporal para revisión visual
```

Los servicios no imprimen mensajes. Devuelven resultados o lanzan errores; la consola confirma el éxito después de completar la transacción. Los errores de persistencia muestran un mensaje genérico y registran el tipo de error, sin contraseñas ni consultas.

Referencias: [scrypt en Python](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt), [conexiones y transacciones con PyMySQL](https://pymysql.readthedocs.io/en/latest/user/examples.html), [seguridad en Flask](https://flask.palletsprojects.com/en/stable/web-security/) y [pruebas de aplicaciones Flask](https://flask.palletsprojects.com/en/stable/testing/).
