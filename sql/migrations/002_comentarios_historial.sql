-- Aplicar después de 001, con respaldo y permisos administrativos.
-- La tabla no altera tickets previos: su historial comienza desde esta actualización.
USE helpdesk;

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
