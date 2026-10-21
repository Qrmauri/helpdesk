-- Revisar SHOW CREATE TABLE antes de aplicar y realizar un respaldo.
-- Requiere la estructura previa: roles, usuarios y tickets.id_usuario.
-- Si actualizado_en ya existe, omitir la segunda sentencia.
-- El DDL de MySQL hace commit implícito: este script no es una transacción reversible.
USE helpdesk;

ALTER TABLE usuarios MODIFY COLUMN password_hash VARCHAR(255) NOT NULL;
ALTER TABLE tickets ADD COLUMN actualizado_en DATETIME NULL;
