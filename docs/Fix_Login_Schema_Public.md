# Fix: `permission denied for schema public` on login

**Date:** 2026-09-28 · **Branch:** `avance2-postgresql-real` · **Flow affected:** `POST /login`

## Symptom

Every login returned HTTP 500, regardless of the password:

```
sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege)
permission denied for schema public
LINE 12:  (public.crypt($1, u.password_hash) = u.password_hash) AS password_ok
```

## Root cause

1. `app/security.py:83` verifies passwords **inside PostgreSQL** with
   `public.crypt(:password, u.password_hash)`.
2. `crypt()` lives in `public` because `sql/01_init_schemas.sql:9` runs
   `CREATE EXTENSION IF NOT EXISTS "pgcrypto";` with no schema qualifier
   (confirmed live: `pgcrypto → public`, `unaccent → public`).
3. An **untracked** leftover script, `sql/01_init_schema_roles.sh`, sat in the
   directory Docker mounts as `docker-entrypoint-initdb.d`, so it ran
   automatically when the volume was initialized. Its line 17 executed
   `REVOKE ALL ON SCHEMA public FROM PUBLIC;` — and no script ever granted
   `USAGE ON SCHEMA public` back to the application roles.

PostgreSQL requires `USAGE` on the containing schema to resolve **any** object
inside it, so the function-level grant was irrelevant:

| Check | Result |
|---|---|
| `has_function_privilege('app_backend','public.crypt(text,text)','EXECUTE')` | `t` |
| `has_schema_privilege('app_backend','public','USAGE')` | **`f`** |
| `public` ACL | `{pg_database_owner=UC/pg_database_owner}` — the default `PUBLIC=U` entry was gone |

The planner aborted before comparing anything, so no password could work.

**Second, latent casualty:** `app/repos/catalogo.py:624` called
`crypt(:password, gen_salt('bf'))` **unqualified**, so creating a user from
`/panel/usuarios` failed with the misleading
`function crypt(unknown, unknown) does not exist`.

Reproduced outside Flask as `app_backend`:

```sql
SELECT public.crypt('x','y');        -- ERROR: permission denied for schema public
SET search_path = operacion,public;
SELECT crypt('x','y');               -- ERROR: function crypt(unknown, unknown) does not exist
SELECT count(*) FROM operacion.rol;  -- 7  (connection/role/password/operacion were fine)
```

## Changes

| File | Change |
|---|---|
| Live database | `GRANT USAGE ON SCHEMA public TO app_backend, app_etl;` |
| `sql/01_init_schemas.sql` | In the permissions `DO $$`: folded in both REVOKEs (database + `public` schema) so the hardening lives in one tracked place, and added `GRANT USAGE ON SCHEMA public` for `app_backend`/`app_etl`, with a comment explaining why `EXECUTE` is not enough. Idempotent. |
| `sql/02_ddl_auditoria.sql` | Preserved the `ALTER DEFAULT PRIVILEGES` for `auditoria` that existed only in the deleted script |
| `sql/03_ddl_operacion.sql` | Added the missing `ALTER DEFAULT PRIVILEGES IN SCHEMA operacion ... TO app_auditor` so tracked scripts match the live `pg_default_acl` |
| `app/repos/catalogo.py` | Qualified as `public.crypt(...)` / `public.gen_salt('bf')`, matching `security.py` |
| `sql/01_init_schema_roles.sh` | **Deleted** — role creation is covered by `00_init_roles.sh` + `bootstrap_db.py`, its grants by `01`/`02`/`03` |
| `scripts/smoke_rutas.py` | `RAIZ = Path(__file__).resolve().parent.parent` (was hardcoded `C:\VSCode\ProyectoIAC`) |
| `AGENTS.md` | New gotcha: `pgcrypto`/`unaccent` live in `public`, so app roles need `USAGE` there |

`GRANT USAGE` (no `CREATE`) is the minimum needed, so the intent of the REVOKE
stays intact. `public` holds **0 tables and 0 views** (only the 40 pgcrypto and
unaccent functions), so nothing else is exposed.

## Verification

* `POST /login` with `admin@freshtrack.mx` / `Admin2026!` → **302 → `/panel`** (was 500); wrong password → clean 200 form error
* As `app_backend`: `public.crypt(...)` → `t`; unqualified variant under the engine `search_path` → `t`; correct password → `t`; wrong password → `f`
* `catalogo.py` insert path exercised inside a rolled-back transaction (no leftover data)
* `make bootstrap` twice → idempotent (`16 objetos clave · 9 usuarios · 7 reglas`)
* `demo_avance2.py --escenario` → exit 0; `--verificar` → exit 0; `smoke_rutas.py` → exit 0, 73 screens × 7 roles all 200
* Fresh-database path checked on a throwaway database (`bootstrap_db.py --db <scratch>`), then dropped

## Notes

* Deleting `sql/01_init_schema_roles.sh` removes no privilege the app needs: `auditoria`
  has 0 sequences and its triggers write through `SECURITY DEFINER` functions
  (`fn_registrar_accion`, `fn_registrar_auditoria`); the affected default ACLs
  were folded into the tracked scripts.
* `sql/01_init_schemas.sql` now enforces `REVOKE ALL ON DATABASE ... FROM PUBLIC`
  at bootstrap time, so `ETL_DATABASE_URL` must remain the superuser (as
  AGENTS.md requires) or bootstrap aborts on that statement.
* `sql/legacy/*.sql` is inert (initdb does not recurse into subdirectories) but
  hardcodes `backend_secure_pass` — a candidate for deletion.
