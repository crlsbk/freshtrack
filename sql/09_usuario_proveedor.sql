-- =============================================================================
-- 09_usuario_proveedor.sql — Liga los usuarios con rol «supplier» a su proveedor
--
-- Cambio mínimo de esquema: UNA columna opcional en operacion.usuario. Idempotente;
-- se aplica en caliente igual que 08:
--
--   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
--     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
--            -f /docker-entrypoint-initdb.d/09_usuario_proveedor.sql'
--
-- Regla (la hace cumplir la aplicación, no un CHECK, para no tocar el rol):
--   un usuario supplier solo ve y modifica productos, órdenes de compra y avisos
--   ASN de SU proveedor; sin proveedor asignado no puede escribir nada.
-- =============================================================================

ALTER TABLE operacion.usuario
    ADD COLUMN IF NOT EXISTS id_proveedor integer
        REFERENCES operacion.proveedor(id_proveedor);

COMMENT ON COLUMN operacion.usuario.id_proveedor IS
    'Proveedor al que representa un usuario con rol supplier (NULL para los demás roles).';

CREATE INDEX IF NOT EXISTS idx_usuario_proveedor
    ON operacion.usuario (id_proveedor) WHERE id_proveedor IS NOT NULL;

-- Usuario de demostración proveedor@freshtrack.mx → Lácteos del Norte.
UPDATE operacion.usuario u
   SET id_proveedor = p.id_proveedor
  FROM operacion.proveedor p
 WHERE lower(u.email) = 'proveedor@freshtrack.mx'
   AND p.rfc = 'LDN850312AA1'
   AND u.id_proveedor IS NULL;

-- Usuarios supplier generados (dataset masivo) sin proveedor: se reparten de
-- forma determinista entre los proveedores activos para que el demo funcione.
-- Un administrador puede reasignarlos desde /usuarios.
WITH sin_proveedor AS (
    SELECT u.id_usuario, row_number() OVER (ORDER BY u.email) - 1 AS n
    FROM operacion.usuario u
    JOIN operacion.rol r ON r.id_rol = u.id_rol
    WHERE r.clave = 'supplier' AND u.id_proveedor IS NULL
),
proveedores AS (
    SELECT id_proveedor, row_number() OVER (ORDER BY id_proveedor) - 1 AS n,
           count(*) OVER () AS total
    FROM operacion.proveedor
    WHERE activo
)
UPDATE operacion.usuario u
   SET id_proveedor = p.id_proveedor
  FROM sin_proveedor s
  JOIN proveedores p ON p.n = s.n % p.total
 WHERE u.id_usuario = s.id_usuario;
