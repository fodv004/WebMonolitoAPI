-- ============================================================
-- 05_triggers.sql
-- Triggers de auditoría e integridad complementaria.
-- ============================================================

-- ------------------------------------------------------------
-- Bitácora de cambios de precio: cada vez que el precio de un
-- libro cambia, se guarda el valor anterior, el nuevo y cuándo
-- ocurrió. Útil para trazabilidad (RNF-07: trazabilidad de errores
-- y cambios).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS libros_precio_historial (
    id_historial   SERIAL PRIMARY KEY,
    isbn           VARCHAR(13) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    precio_anterior NUMERIC(10,2) NOT NULL,
    precio_nuevo    NUMERIC(10,2) NOT NULL,
    fecha_cambio    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION trg_fn_registrar_cambio_precio()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.precio IS DISTINCT FROM OLD.precio THEN
        INSERT INTO libros_precio_historial (isbn, precio_anterior, precio_nuevo)
        VALUES (OLD.isbn, OLD.precio, NEW.precio);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_registrar_cambio_precio
    AFTER UPDATE ON libros
    FOR EACH ROW
    EXECUTE FUNCTION trg_fn_registrar_cambio_precio();

-- ------------------------------------------------------------
-- Numeración automática de imágenes: al insertar una imagen sin
-- especificar 'orden', se le asigna automáticamente el siguiente
-- número dentro de ese libro (evita que la aplicación tenga que
-- calcularlo manualmente).
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_auto_orden_imagen()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.orden IS NULL THEN
        SELECT COALESCE(MAX(orden), -1) + 1
        INTO NEW.orden
        FROM imagenes
        WHERE isbn = NEW.isbn;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auto_orden_imagen
    BEFORE INSERT ON imagenes
    FOR EACH ROW
    EXECUTE FUNCTION trg_fn_auto_orden_imagen();

-- ------------------------------------------------------------
-- Normalización de correo: guarda siempre el correo en minúsculas,
-- para que 'Usuario@Correo.com' y 'usuario@correo.com' no se traten
-- como cuentas distintas al momento de iniciar sesión.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_normalizar_correo()
RETURNS TRIGGER AS $$
BEGIN
    NEW.correo := LOWER(TRIM(NEW.correo));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_normalizar_correo
    BEFORE INSERT OR UPDATE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION trg_fn_normalizar_correo();
