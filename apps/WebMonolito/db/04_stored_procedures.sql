-- ============================================================
-- 04_stored_procedures.sql
-- Funciones/procedimientos almacenados para las operaciones
-- de negocio más usadas por la aplicación.
-- ============================================================

-- ------------------------------------------------------------
-- sp_crear_libro: crea un libro validando que el formato exista
-- (la FK ya lo garantiza; la función solo centraliza la operación)
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sp_crear_libro(
    p_isbn VARCHAR(13),
    p_titulo VARCHAR(255),
    p_anio SMALLINT,
    p_precio NUMERIC(10,2),
    p_stock INTEGER,
    p_id_formato INTEGER
) RETURNS VOID AS $$
BEGIN
    INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato)
    VALUES (p_isbn, p_titulo, p_anio, p_precio, p_stock, p_id_formato);
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- sp_actualizar_stock: ajusta el stock de un libro sumando/restando
-- una cantidad (positiva o negativa), sin permitir que quede negativo.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sp_actualizar_stock(
    p_isbn VARCHAR(13),
    p_cantidad INTEGER
) RETURNS VOID AS $$
DECLARE
    v_stock_actual INTEGER;
BEGIN
    SELECT stock INTO v_stock_actual FROM libros WHERE isbn = p_isbn;

    IF v_stock_actual IS NULL THEN
        RAISE EXCEPTION 'El libro con ISBN % no existe', p_isbn;
    END IF;

    IF v_stock_actual + p_cantidad < 0 THEN
        RAISE EXCEPTION 'Operación inválida: el stock resultante sería negativo';
    END IF;

    UPDATE libros SET stock = stock + p_cantidad WHERE isbn = p_isbn;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- sp_eliminar_libro: elimina un libro (las relaciones dependientes
-- se limpian solas por ON DELETE CASCADE definido en el esquema).
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sp_eliminar_libro(p_isbn VARCHAR(13))
RETURNS VOID AS $$
BEGIN
    DELETE FROM libros WHERE isbn = p_isbn;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El libro con ISBN % no existe', p_isbn;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- sp_asociar_autor_libro: asocia un autor a un libro evitando
-- duplicados silenciosamente (ON CONFLICT DO NOTHING).
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sp_asociar_autor_libro(
    p_isbn VARCHAR(13),
    p_id_autor INTEGER
) RETURNS VOID AS $$
BEGIN
    INSERT INTO libro_autor (isbn, id_autor)
    VALUES (p_isbn, p_id_autor)
    ON CONFLICT (isbn, id_autor) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- sp_registrar_usuario: registra un usuario nuevo. Recibe el
-- password_hash ya generado por la aplicación (bcrypt) — la
-- función NO hashea contraseñas, solo persiste el registro.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sp_registrar_usuario(
    p_nombre VARCHAR(150),
    p_correo VARCHAR(150),
    p_password_hash VARCHAR(255)
) RETURNS INTEGER AS $$
DECLARE
    v_id_usuario INTEGER;
BEGIN
    INSERT INTO usuarios (nombre, correo, password_hash, es_admin)
    VALUES (p_nombre, p_correo, p_password_hash, FALSE)
    RETURNING id_usuario INTO v_id_usuario;

    RETURN v_id_usuario;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- sp_buscar_libros: búsqueda por ISBN exacto o coincidencia
-- parcial de título (usada por el punto RF-05 de búsqueda).
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sp_buscar_libros(p_texto VARCHAR)
RETURNS SETOF libros AS $$
    SELECT * FROM libros
    WHERE isbn = p_texto OR titulo ILIKE '%' || p_texto || '%';
$$ LANGUAGE sql STABLE;

-- ------------------------------------------------------------
-- sp_marcar_imagen_principal: marca una imagen como portada,
-- desmarcando cualquier otra portada previa del mismo libro
-- (evita chocar con el índice único una_imagen_principal).
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION sp_marcar_imagen_principal(p_id_imagen INTEGER)
RETURNS VOID AS $$
DECLARE
    v_isbn VARCHAR(13);
BEGIN
    SELECT isbn INTO v_isbn FROM imagenes WHERE id_imagen = p_id_imagen;

    IF v_isbn IS NULL THEN
        RAISE EXCEPTION 'La imagen % no existe', p_id_imagen;
    END IF;

    UPDATE imagenes SET es_principal = FALSE WHERE isbn = v_isbn;
    UPDATE imagenes SET es_principal = TRUE WHERE id_imagen = p_id_imagen;
END;
$$ LANGUAGE plpgsql;
