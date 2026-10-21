# Helpdesk — SurSoporte Ltda.

Sistema de soporte técnico en consola, escrito en Python y respaldado por MySQL. Permite registrar usuarios, iniciar sesión, crear y asignar tickets y gestionar su ciclo de atención.

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

El script crea la base `helpdesk`, las tablas `roles`, `usuarios` y `tickets`, los tres roles, índices y restricciones. No crea usuarios de la aplicación ni incluye contraseñas predeterminadas. Úsalo solo para una instalación nueva: fallará si las tablas ya existen.

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

Se validan usuarios de 3 a 50 caracteres, emails de hasta 254, contraseñas nuevas de 10 a 128, títulos de 1 a 200 y descripciones de 1 a 10000. El formato de correo se comprueba de forma básica; no se verifica la propiedad de la dirección. No hay comentarios, adjuntos ni recuperación de contraseñas en esta versión.

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

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Las pruebas usan `unittest` y conexiones simuladas; no requieren un servidor ni modifican una base real. Cubren autenticación, migración de hashes, roles, validaciones, permisos, estados, rollback y mensajes de la consola. No sustituyen una prueba de integración con el esquema real.

Para comprobar la instalación en una base de prueba:

1. Importa el esquema y configura las variables de entorno.
2. Registra un publicador, un futuro agente y el futuro supervisor; comprueba que no se aceptan duplicados ni datos inválidos.
3. Promueve al supervisor desde MySQL y al agente desde su menú.
4. Crea un ticket como publicador, asígnalo como supervisor y recorre sus estados como agente.
5. Comprueba que un agente ajeno no puede modificarlo, que el cerrado no se puede asignar y que solo un supervisor puede reabrirlo.
6. Detén el servidor de prueba y confirma que aparece un error sin anunciar éxito ni mostrar detalles internos SQL.

## Estructura

```text
main.py                         Arranque y composición de servicios
ui/menu.py                      Entradas y mensajes de consola
services/auth_service.py         Autenticación, contraseñas y roles
services/ticket_service.py       Casos de uso de tickets
src/domain/                     Usuario, Ticket, reglas y errores
infra/db.py                     Conexiones y transacciones
infra/repositories/              Consultas de usuarios
sql/schema.sql                  Esquema para instalaciones nuevas
sql/migrations/                 Cambios revisables para bases previas
tests/test_regressions.py        Pruebas automatizadas
```

Los servicios no imprimen mensajes. Devuelven resultados o lanzan errores; la consola confirma el éxito después de completar la transacción. Los errores de persistencia muestran un mensaje genérico y registran el tipo de error, sin contraseñas ni consultas.

Referencias: [scrypt en Python](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt) y [conexiones y transacciones con PyMySQL](https://pymysql.readthedocs.io/en/latest/user/examples.html).
