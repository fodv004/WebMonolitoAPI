-- ============================================================
-- 02_seed_30_per_table.sql (v2 — datos realistas)
--
-- Libros, autores, géneros y conceptos son obras y relaciones reales
-- (no aleatorias): cada libro está asociado a su autor verdadero y a
-- géneros/conceptos temáticamente correctos.
--
-- Imágenes: se usan URLs de Picsum Photos (https://picsum.photos),
-- un servicio público que SIEMPRE devuelve una imagen real y cargable.
-- No se usan portadas reales de los libros para evitar problemas de
-- derechos de autor en un proyecto académico público.
--
-- ISBNs: son sintéticos (no corresponden a ediciones reales), para no
-- arriesgar publicar un ISBN real incorrecto o de otra obra.
-- ============================================================

-- ---------- 1. Catálogos acotados ----------

INSERT INTO formatos (nombre) VALUES
    ('Tapa dura'), ('Tapa blanda'), ('Digital'), ('Audiolibro'), ('Pasta rústica');

INSERT INTO generos (nombre) VALUES
    ('Ficción'), ('Ciencia'), ('Historia'), ('Realismo mágico'), ('Poesía'),
    ('Terror'), ('Fantasía'), ('Ciencia ficción'), ('Biografía'), ('Ensayo'),
    ('Filosofía'), ('Novela negra'), ('Romance'), ('Aventura'), ('Infantil');

-- ---------- 2. Autores (30, reales) ----------

INSERT INTO autores (nombre, nacionalidad) VALUES
    ('Gabriel García Márquez', 'Colombiana'),      -- 1
    ('Isabel Allende', 'Chilena'),                  -- 2
    ('Julio Cortázar', 'Argentina'),                -- 3
    ('Jorge Luis Borges', 'Argentina'),             -- 4
    ('Mario Vargas Llosa', 'Peruana'),              -- 5
    ('Octavio Paz', 'Mexicana'),                    -- 6
    ('Pablo Neruda', 'Chilena'),                    -- 7
    ('Laura Esquivel', 'Mexicana'),                 -- 8
    ('Juan Rulfo', 'Mexicana'),                     -- 9
    ('Carlos Fuentes', 'Mexicana'),                 -- 10
    ('Roberto Bolaño', 'Chilena'),                  -- 11
    ('Elena Poniatowska', 'Mexicana'),              -- 12
    ('José Saramago', 'Portuguesa'),                -- 13
    ('Miguel de Cervantes', 'Española'),            -- 14
    ('Federico García Lorca', 'Española'),          -- 15
    ('George Orwell', 'Británica'),                 -- 16
    ('Virginia Woolf', 'Británica'),                -- 17
    ('Jane Austen', 'Británica'),                   -- 18
    ('Ernest Hemingway', 'Estadounidense'),         -- 19
    ('Toni Morrison', 'Estadounidense'),            -- 20
    ('Franz Kafka', 'Checa'),                       -- 21
    ('Fiodor Dostoyevski', 'Rusa'),                 -- 22
    ('León Tolstói', 'Rusa'),                       -- 23
    ('Haruki Murakami', 'Japonesa'),                -- 24
    ('Yukio Mishima', 'Japonesa'),                  -- 25
    ('Albert Camus', 'Francesa'),                   -- 26
    ('Victor Hugo', 'Francesa'),                    -- 27
    ('Umberto Eco', 'Italiana'),                    -- 28
    ('Italo Calvino', 'Italiana'),                  -- 29
    ('J.R.R. Tolkien', 'Británica');                -- 30

-- ---------- 3. Conceptos (20) ----------

INSERT INTO conceptos (nombre) VALUES
    ('Realismo mágico'), ('Soledad'), ('Memoria histórica'), ('Identidad'),
    ('Distopía'), ('Absurdo'), ('Existencialismo'), ('Alienación'),
    ('Metaficción'), ('Nostalgia'), ('Guerra'), ('Amor romántico'),
    ('Muerte'), ('Tiempo circular'), ('Colonialismo'), ('Migración'),
    ('Poder'), ('Libertad'), ('Justicia social'), ('Naturaleza humana');

-- ---------- 4. Usuarios: 1 administrador + 29 registrados (nombres reales) ----------

-- Administrador: reemplaza el password_hash por un hash bcrypt real antes de usar
-- (ver README.md — node -e "require('bcrypt').hash('tu_password',12).then(console.log)")
INSERT INTO usuarios (nombre, correo, password_hash, es_admin)
VALUES ('Admin Principal', 'admin@libreria.com', 'CAMBIAR_POR_HASH_BCRYPT_REAL', TRUE);

DO $$
DECLARE
    nombres TEXT[] := ARRAY[
        'María Fernanda López', 'José Luis Hernández', 'Ana Sofía Martínez', 'Diego Alejandro Ramírez',
        'Valentina Torres', 'Santiago Gómez', 'Camila Rodríguez', 'Mateo Sánchez',
        'Regina Flores', 'Emiliano Cruz', 'Ximena Morales', 'Sebastián Ortiz',
        'Daniela Reyes', 'Alejandro Jiménez', 'Fernanda Castillo', 'Leonardo Vázquez',
        'Paulina Mendoza', 'Rodrigo Ruiz', 'Isabella Guzmán', 'Nicolás Aguilar',
        'Renata Vargas', 'Adrián Castro', 'Mariana Ríos', 'Gael Delgado',
        'Sofía Navarro', 'Ángel Domínguez', 'Victoria Chávez', 'Iker Salazar',
        'Natalia Peña'
    ];
    correos TEXT[] := ARRAY[
        'maria.lopez', 'jose.hernandez', 'ana.martinez', 'diego.ramirez',
        'valentina.torres', 'santiago.gomez', 'camila.rodriguez', 'mateo.sanchez',
        'regina.flores', 'emiliano.cruz', 'ximena.morales', 'sebastian.ortiz',
        'daniela.reyes', 'alejandro.jimenez', 'fernanda.castillo', 'leonardo.vazquez',
        'paulina.mendoza', 'rodrigo.ruiz', 'isabella.guzman', 'nicolas.aguilar',
        'renata.vargas', 'adrian.castro', 'mariana.rios', 'gael.delgado',
        'sofia.navarro', 'angel.dominguez', 'victoria.chavez', 'iker.salazar',
        'natalia.pena'
    ];
    i INTEGER;
BEGIN
    FOR i IN 1..29 LOOP
        INSERT INTO usuarios (nombre, correo, password_hash, es_admin)
        VALUES (nombres[i], correos[i] || '@libreria.com', 'demo1234', FALSE);
    END LOOP;
END $$;

-- ---------- 5. Libros (30, obras reales con su autor verdadero) ----------

DO $$
DECLARE
    i INTEGER;
    -- índice = mismo id_autor (1..30) del autor correspondiente a cada libro
    titulos TEXT[] := ARRAY[
        'Cien años de soledad', 'La casa de los espíritus', 'Rayuela', 'Ficciones',
        'La ciudad y los perros', 'El laberinto de la soledad',
        'Veinte poemas de amor y una canción desesperada', 'Como agua para chocolate',
        'Pedro Páramo', 'La región más transparente', '2666', 'La noche de Tlatelolco',
        'Ensayo sobre la ceguera', 'Don Quijote de la Mancha', 'Romancero gitano',
        '1984', 'Mrs. Dalloway', 'Orgullo y prejuicio', 'El viejo y el mar', 'Beloved',
        'La metamorfosis', 'Crimen y castigo', 'Guerra y paz', 'Tokio Blues',
        'Confesiones de una máscara', 'El extranjero', 'Los miserables',
        'El nombre de la rosa', 'Las ciudades invisibles', 'El hobbit'
    ];
    anios INTEGER[] := ARRAY[
        1967,1982,1963,1944,1963,1950,1924,1989,1955,1958,2004,1971,
        1995,1605,1928,1949,1925,1813,1952,1987,1915,1866,1869,1987,
        1949,1942,1862,1980,1972,1937
    ];
BEGIN
    FOR i IN 1..30 LOOP
        INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato)
        VALUES (
            '978' || LPAD(i::TEXT, 10, '0'),
            titulos[i],
            anios[i],
            (150 + (i * 12))::NUMERIC(10,2),
            (i % 25) + 1,
            ((i - 1) % 5) + 1
        );
        -- Cada libro con su autor real (mismo índice i = mismo id_autor)
        INSERT INTO libro_autor (isbn, id_autor) VALUES ('978' || LPAD(i::TEXT, 10, '0'), i);
    END LOOP;
END $$;

-- Asociaciones adicionales de autor (demostración de la relación M:N —
-- agrupadas por movimiento literario compartido, no coautoría real):
INSERT INTO libro_autor (isbn, id_autor) VALUES
    ('9780000000001', 5),  -- Cien años de soledad + Vargas Llosa (Boom latinoamericano)
    ('9780000000003', 4),  -- Rayuela + Borges (vanguardia argentina)
    ('9780000000016', 26); -- 1984 + Camus (literatura de posguerra, edición comentada)

-- ---------- 6. libro_genero (géneros reales por temática de cada obra) ----------

INSERT INTO libro_genero (isbn, id_genero) VALUES
    ('9780000000001', 1), ('9780000000001', 4),   -- Cien años de soledad: Ficción, Realismo mágico
    ('9780000000002', 1), ('9780000000002', 4),   -- La casa de los espíritus
    ('9780000000003', 1),                          -- Rayuela: Ficción
    ('9780000000004', 1), ('9780000000004', 7),   -- Ficciones: Ficción, Fantasía
    ('9780000000005', 1),                          -- La ciudad y los perros
    ('9780000000006', 10), ('9780000000006', 11), -- El laberinto de la soledad: Ensayo, Filosofía
    ('9780000000007', 5),                          -- Veinte poemas de amor: Poesía
    ('9780000000008', 1), ('9780000000008', 13),  -- Como agua para chocolate: Ficción, Romance
    ('9780000000009', 1), ('9780000000009', 4),   -- Pedro Páramo: Ficción, Realismo mágico
    ('9780000000010', 1),                          -- La región más transparente
    ('9780000000011', 1), ('9780000000011', 12),  -- 2666: Ficción, Novela negra
    ('9780000000012', 3), ('9780000000012', 10),  -- La noche de Tlatelolco: Historia, Ensayo
    ('9780000000013', 1),                          -- Ensayo sobre la ceguera
    ('9780000000014', 1), ('9780000000014', 14),  -- Don Quijote: Ficción, Aventura
    ('9780000000015', 5),                          -- Romancero gitano: Poesía
    ('9780000000016', 8),                          -- 1984: Ciencia ficción
    ('9780000000017', 1),                          -- Mrs. Dalloway
    ('9780000000018', 13),                         -- Orgullo y prejuicio: Romance
    ('9780000000019', 1), ('9780000000019', 14),  -- El viejo y el mar: Ficción, Aventura
    ('9780000000020', 1), ('9780000000020', 3),   -- Beloved: Ficción, Historia
    ('9780000000021', 1),                          -- La metamorfosis
    ('9780000000022', 12), ('9780000000022', 1),  -- Crimen y castigo: Novela negra, Ficción
    ('9780000000023', 3), ('9780000000023', 1),   -- Guerra y paz: Historia, Ficción
    ('9780000000024', 13), ('9780000000024', 1),  -- Tokio Blues: Romance, Ficción
    ('9780000000025', 1),                          -- Confesiones de una máscara
    ('9780000000026', 11), ('9780000000026', 1),  -- El extranjero: Filosofía, Ficción
    ('9780000000027', 1), ('9780000000027', 3),   -- Los miserables: Ficción, Historia
    ('9780000000028', 12), ('9780000000028', 3),  -- El nombre de la rosa: Novela negra, Historia
    ('9780000000029', 7), ('9780000000029', 1),   -- Las ciudades invisibles: Fantasía, Ficción
    ('9780000000030', 7), ('9780000000030', 14);  -- El hobbit: Fantasía, Aventura

-- ---------- 7. libro_concepto (conceptos reales por temática de cada obra) ----------

INSERT INTO libro_concepto (isbn, id_concepto, definicion) VALUES
    ('9780000000001', 1, 'Técnica narrativa donde eventos fantásticos se presentan como parte de la realidad cotidiana; rasgo definitorio de la obra.'),
    ('9780000000001', 2, 'Tema central que recorre a varias generaciones de la familia Buendía, marcadas por el aislamiento emocional y el destino.'),
    ('9780000000001', 14, 'La narrativa sugiere que la historia de Macondo se repite en ciclos, como si el tiempo no avanzara linealmente.'),
    ('9780000000009', 1, 'Los muertos conviven con los vivos en Comala como parte natural del mundo narrado, sin distinguirse como sobrenatural.'),
    ('9780000000012', 3, 'Testimonio periodístico que documenta la matanza de Tlatelolco de 1968 desde voces de sobrevivientes.'),
    ('9780000000016', 5, 'Retrato de un régimen totalitario que controla la información y vigila a sus ciudadanos mediante el Gran Hermano.'),
    ('9780000000016', 17, 'El Partido ejerce control absoluto sobre la verdad, el lenguaje y el pensamiento de la población.'),
    ('9780000000021', 6, 'Gregorio Samsa despierta convertido en insecto sin explicación alguna, y la historia nunca justifica el porqué.'),
    ('9780000000021', 8, 'El protagonista queda progresivamente aislado de su familia y de la sociedad tras su transformación.'),
    ('9780000000026', 7, 'Meursault enfrenta la muerte de su madre y su propio juicio con una indiferencia que refleja la filosofía del absurdo.'),
    ('9780000000026', 13, 'La cercanía de la muerte y su aceptación sin consuelo religioso es tema central de la novela.'),
    ('9780000000003', 9, 'La novela permite leerse en distinto orden de capítulos, cuestionando la forma tradicional de contar una historia.'),
    ('9780000000020', 4, 'La protagonista, una mujer que escapó de la esclavitud, lucha por reconstruir su identidad y la de su familia.'),
    ('9780000000020', 15, 'La novela aborda las heridas del sistema esclavista estadounidense y sus consecuencias generacionales.'),
    ('9780000000027', 19, 'Jean Valjean y otros personajes enfrentan un sistema legal y social que perpetúa la pobreza y la desigualdad.'),
    ('9780000000018', 12, 'La relación entre Elizabeth Bennet y Mr. Darcy explora el amor a través de prejuicios sociales y de clase.'),
    ('9780000000022', 20, 'Raskólnikov comete un crimen que lo enfrenta a su propia conciencia moral y a la naturaleza humana.'),
    ('9780000000023', 11, 'La novela sigue a varias familias rusas durante las guerras napoleónicas y su impacto en la sociedad.');

-- ---------- 8. imagenes: 1 portada real (Picsum) por libro + segunda imagen ocasional ----------

DO $$
DECLARE
    i INTEGER;
BEGIN
    FOR i IN 1..30 LOOP
        INSERT INTO imagenes (isbn, url, es_principal, orden)
        VALUES (
            '978' || LPAD(i::TEXT, 10, '0'),
            'https://picsum.photos/seed/libro' || i || '/400/600',
            TRUE,
            0
        );

        IF i % 4 = 0 THEN
            INSERT INTO imagenes (isbn, url, es_principal, orden)
            VALUES (
                '978' || LPAD(i::TEXT, 10, '0'),
                'https://picsum.photos/seed/libro' || i || 'b/400/600',
                FALSE,
                1
            );
        END IF;
    END LOOP;
END $$;
