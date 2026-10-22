-- Solo para instalaciones nuevas. No ejecutar sobre tablas existentes.
CREATE DATABASE IF NOT EXISTS helpdesk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE helpdesk;

CREATE TABLE roles (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(20) NOT NULL UNIQUE,
    CONSTRAINT chk_roles_nombre CHECK (nombre IN ('PUBLICADOR', 'AGENTE', 'SUPERVISOR'))
) ENGINE=InnoDB;

INSERT INTO roles (nombre) VALUES ('PUBLICADOR'), ('AGENTE'), ('SUPERVISOR');

CREATE TABLE usuarios (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    id_rol INT NOT NULL,
    CONSTRAINT fk_usuarios_rol FOREIGN KEY (id_rol) REFERENCES roles(id)
) ENGINE=InnoDB;

CREATE TABLE tickets (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'ABIERTO',
    id_usuario INT NOT NULL,
    asignado_a INT NULL,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en DATETIME NULL,
    INDEX idx_tickets_autor (id_usuario),
    INDEX idx_tickets_asignado (asignado_a),
    CONSTRAINT fk_tickets_autor FOREIGN KEY (id_usuario) REFERENCES usuarios(id),
    CONSTRAINT fk_tickets_agente FOREIGN KEY (asignado_a) REFERENCES usuarios(id),
    CONSTRAINT chk_tickets_estado CHECK (estado IN ('ABIERTO', 'EN_PROCESO', 'EN_ESPERA', 'RESUELTO', 'CERRADO'))
) ENGINE=InnoDB;

CREATE TABLE ticket_actividad (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    usuario_id INT NOT NULL,
    tipo VARCHAR(20) NOT NULL,
    contenido TEXT NOT NULL,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_actividad_ticket (ticket_id, id),
    CONSTRAINT fk_actividad_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    CONSTRAINT fk_actividad_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    CONSTRAINT chk_actividad_tipo CHECK (tipo IN ('CREADO', 'ASIGNADO', 'ESTADO', 'COMENTARIO'))
) ENGINE=InnoDB;
