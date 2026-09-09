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

-- Asignar correos oficiales a cada rol para inicio de sesión inmediato
UPDATE operacion.usuario SET email = 'admin@freshtrack.mx' WHERE id_usuario = (SELECT u.id_usuario FROM operacion.usuario u JOIN operacion.rol r ON r.id_rol = u.id_rol WHERE r.nombre_rol = 'Administrador' LIMIT 1);
UPDATE operacion.usuario SET email = 'store_manager@freshtrack.mx' WHERE id_usuario = (SELECT u.id_usuario FROM operacion.usuario u JOIN operacion.rol r ON r.id_rol = u.id_rol WHERE r.nombre_rol = 'Gerente de Tienda' LIMIT 1);
UPDATE operacion.usuario SET email = 'buyer@freshtrack.mx' WHERE id_usuario = (SELECT u.id_usuario FROM operacion.usuario u JOIN operacion.rol r ON r.id_rol = u.id_rol WHERE r.nombre_rol = 'Comprador' LIMIT 1);
UPDATE operacion.usuario SET email = 'demand_planner@freshtrack.mx' WHERE id_usuario = (SELECT u.id_usuario FROM operacion.usuario u JOIN operacion.rol r ON r.id_rol = u.id_rol WHERE r.nombre_rol = 'Planeador de Demanda' LIMIT 1);
UPDATE operacion.usuario SET email = 'warehouse_operator@freshtrack.mx' WHERE id_usuario = (SELECT u.id_usuario FROM operacion.usuario u JOIN operacion.rol r ON r.id_rol = u.id_rol WHERE r.nombre_rol = 'Operador de Almacén' LIMIT 1);
UPDATE operacion.usuario SET email = 'auditor@freshtrack.mx' WHERE id_usuario = (SELECT u.id_usuario FROM operacion.usuario u JOIN operacion.rol r ON r.id_rol = u.id_rol WHERE r.nombre_rol = 'Auditor' LIMIT 1);