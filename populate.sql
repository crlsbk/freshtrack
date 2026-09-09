-- pegar esto adentro de psql--
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE operacion.usuario
ADD COLUMN email VARCHAR(255) UNIQUE,
ADD COLUMN password_hash TEXT;

UPDATE operacion.usuario
SET
    email =
        lower(
            regexp_replace(
                unaccent(nombre_completo),
                '[^a-zA-Z0-9]+',
                '.',
                'g'
            )
        )
        || '.' || left(id_usuario::text, 8)
        || '@freshtrack.mx',

    password_hash = crypt('freshtrack', gen_salt('bf'))
WHERE email IS NULL
   OR password_hash IS NULL;