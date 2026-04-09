-- ============================================================
-- Clínica — Esquema PostgreSQL
-- ============================================================

-- Extensión para UUIDs (opcional, si quieres migrar a UUID en el futuro)
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Configuración del turno ──────────────────────────────────
CREATE TABLE IF NOT EXISTS turno_config (
    id              INTEGER         PRIMARY KEY DEFAULT 1,
    clinica_nombre  VARCHAR(200)    NOT NULL DEFAULT 'Centro Médico Norte',
    hora_apertura   TIME            NOT NULL DEFAULT '07:00',
    hora_cierre     TIME            NOT NULL DEFAULT '19:00',
    fecha           DATE            NOT NULL DEFAULT CURRENT_DATE,

    CONSTRAINT turno_config_single_row CHECK (id = 1)
);

-- ── Pacientes ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pacientes (
    id                      SERIAL          PRIMARY KEY,
    nombre                  VARCHAR(200)    NOT NULL,
    edad                    SMALLINT        CHECK (edad >= 0 AND edad <= 150),
    fecha_atencion          DATE            NOT NULL DEFAULT CURRENT_DATE,
    hora_ingreso            TIME,
    hora_egreso             TIME,
    diagnostico_principal   VARCHAR(300),
    diagnostico_codigo      VARCHAR(20),    -- Código CIE-10
    medico                  VARCHAR(200),
    estado                  VARCHAR(50)     NOT NULL DEFAULT 'atendido'
                                            CHECK (estado IN ('atendido', 'pendiente', 'cancelado', 'derivado'))
);

CREATE INDEX IF NOT EXISTS idx_pacientes_fecha    ON pacientes (fecha_atencion);
CREATE INDEX IF NOT EXISTS idx_pacientes_medico   ON pacientes (medico);
CREATE INDEX IF NOT EXISTS idx_pacientes_diag     ON pacientes (diagnostico_codigo);

-- ── Medicamentos ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medicamentos (
    id              SERIAL          PRIMARY KEY,
    nombre          VARCHAR(200)    NOT NULL,
    categoria       VARCHAR(100),
    stock_actual    INTEGER         NOT NULL DEFAULT 0   CHECK (stock_actual >= 0),
    stock_minimo    INTEGER         NOT NULL DEFAULT 10  CHECK (stock_minimo >= 0),
    unidad          VARCHAR(50)     NOT NULL DEFAULT 'unidades',
    precio_unitario NUMERIC(10, 2)  NOT NULL DEFAULT 0.00
);

CREATE INDEX IF NOT EXISTS idx_medicamentos_nombre ON medicamentos (nombre);

-- ── Dispensaciones ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dispensacion (
    id              SERIAL      PRIMARY KEY,
    medicamento_id  INTEGER     NOT NULL REFERENCES medicamentos(id) ON DELETE RESTRICT,
    cantidad        INTEGER     NOT NULL CHECK (cantidad > 0),
    fecha           DATE        NOT NULL DEFAULT CURRENT_DATE,
    paciente_id     INTEGER     REFERENCES pacientes(id) ON DELETE SET NULL,
    motivo          VARCHAR(300)
);

CREATE INDEX IF NOT EXISTS idx_dispensacion_fecha  ON dispensacion (fecha);
CREATE INDEX IF NOT EXISTS idx_dispensacion_med    ON dispensacion (medicamento_id);

-- ============================================================
-- Datos de prueba (ejecutar solo en desarrollo)
-- ============================================================

INSERT INTO turno_config (id, clinica_nombre, hora_apertura, hora_cierre, fecha)
VALUES (1, 'Centro Médico Norte', '07:00', '19:00', CURRENT_DATE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO medicamentos (nombre, categoria, stock_actual, stock_minimo, unidad, precio_unitario) VALUES
    ('Metformina 850mg',    'Antidiabético',    45,  20, 'tabletas',  0.15),
    ('Enalapril 10mg',      'Antihipertensivo', 82,  25, 'tabletas',  0.08),
    ('Losartán 50mg',       'Antihipertensivo',  0,  15, 'tabletas',  0.22),  -- stock cero
    ('Amoxicilina 500mg',   'Antibiótico',      120, 30, 'cápsulas',  0.18),
    ('Ibuprofeno 400mg',    'Antiinflamatorio',   8, 20, 'tabletas',  0.05),  -- bajo
    ('Omeprazol 20mg',      'Gastroprotector',   95, 20, 'cápsulas',  0.12),
    ('Paracetamol 500mg',   'Analgésico',       200, 50, 'tabletas',  0.03),
    ('Ciprofloxacino 500mg','Antibiótico',       35, 15, 'tabletas',  0.35),
    ('Amlodipino 5mg',      'Antihipertensivo',  67, 20, 'tabletas',  0.10),
    ('Insulina NPH',        'Antidiabético',     12,  8, 'frascos',   8.50)
ON CONFLICT DO NOTHING;

INSERT INTO pacientes (nombre, edad, fecha_atencion, hora_ingreso, hora_egreso, diagnostico_principal, diagnostico_codigo, medico) VALUES
    ('María García',    45, CURRENT_DATE, '07:15', '08:30', 'Hipertensión arterial',         'I10', 'Dr. Rodríguez'),
    ('Carlos Mendez',   67, CURRENT_DATE, '07:45', '09:00', 'Diabetes mellitus tipo 2',      'E11', 'Dra. Torres'),
    ('Ana Jiménez',     32, CURRENT_DATE, '08:00', '08:45', 'Infección respiratoria aguda',  'J06', 'Dr. Rodríguez'),
    ('Luis Pérez',      58, CURRENT_DATE, '08:30', '09:30', 'Hipertensión arterial',         'I10', 'Dra. Torres'),
    ('Carmen López',    41, CURRENT_DATE, '09:00', '10:00', 'Diabetes mellitus tipo 2',      'E11', 'Dr. Rodríguez'),
    ('Roberto Silva',   29, CURRENT_DATE, '09:30', '10:15', 'Lumbalgia',                     'M54', 'Dra. Torres'),
    ('Patricia Ruiz',   55, CURRENT_DATE, '10:00', '11:00', 'Infección respiratoria aguda',  'J06', 'Dr. Rodríguez'),
    ('Miguel Castro',   72, CURRENT_DATE, '10:30', '11:45', 'Hipertensión arterial',         'I10', 'Dra. Torres'),
    ('Isabel Moreno',   38, CURRENT_DATE, '11:00', '11:45', 'Gastritis crónica',             'K29', 'Dr. Rodríguez'),
    ('Fernando Vega',   49, CURRENT_DATE, '11:30', '12:30', 'Diabetes mellitus tipo 2',      'E11', 'Dra. Torres'),
    ('Sofía Herrera',   26, CURRENT_DATE, '12:00', '12:45', 'Infección urinaria',            'N39', 'Dr. Rodríguez'),
    ('Diego Ramírez',   63, CURRENT_DATE, '14:00', '15:00', 'Hipertensión arterial',         'I10', 'Dra. Torres'),
    ('Laura Flores',    44, CURRENT_DATE, '14:30', '15:30', 'Lumbalgia',                     'M54', 'Dr. Rodríguez'),
    ('Andrés Vargas',   51, CURRENT_DATE, '15:00', '16:00', 'Gastritis crónica',             'K29', 'Dra. Torres'),
    ('Valentina Cruz',  35, CURRENT_DATE, '15:30', '16:15', 'Infección respiratoria aguda',  'J06', 'Dr. Rodríguez');

INSERT INTO dispensacion (medicamento_id, cantidad, fecha, paciente_id, motivo) VALUES
    (1, 10, CURRENT_DATE,  2, 'Tratamiento DM2'),
    (1, 15, CURRENT_DATE,  5, 'Tratamiento DM2'),
    (1, 10, CURRENT_DATE, 10, 'Tratamiento DM2'),
    (2, 30, CURRENT_DATE,  1, 'Tratamiento HTA'),
    (2, 30, CURRENT_DATE,  4, 'Tratamiento HTA'),
    (2, 30, CURRENT_DATE,  8, 'Tratamiento HTA'),
    (4, 21, CURRENT_DATE,  3, 'Infección resp'),
    (4, 21, CURRENT_DATE,  7, 'Infección resp'),
    (4, 21, CURRENT_DATE, 11, 'Infección resp'),
    (5, 20, CURRENT_DATE,  6, 'Lumbalgia'),
    (5, 20, CURRENT_DATE, 13, 'Lumbalgia'),
    (6, 28, CURRENT_DATE,  9, 'Gastroprotección'),
    (7, 60, CURRENT_DATE, 14, 'Analgesia'),
    (9, 30, CURRENT_DATE, 12, 'Tratamiento HTA');
