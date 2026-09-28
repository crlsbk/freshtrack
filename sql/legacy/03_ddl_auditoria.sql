--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: auditoria; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA auditoria;


ALTER SCHEMA auditoria OWNER TO postgres;

--
-- Name: fn_bloquear_modificacion_auditoria(); Type: FUNCTION; Schema: auditoria; Owner: postgres
--

CREATE FUNCTION auditoria.fn_bloquear_modificacion_auditoria() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'Violación de seguridad: No está permitido alterar o eliminar registros de la bitácora de auditoría.';
    RETURN NULL;
END;
$$;


ALTER FUNCTION auditoria.fn_bloquear_modificacion_auditoria() OWNER TO postgres;

--
-- Name: fn_registrar_auditoria(); Type: FUNCTION; Schema: auditoria; Owner: postgres
--

CREATE FUNCTION auditoria.fn_registrar_auditoria() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
DECLARE
    v_user_id UUID;
BEGIN
    -- Captura el UUID del usuario real desde una variable de sesión configurada por el backend
    BEGIN
        v_user_id := current_setting('app.current_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        v_user_id := NULL; -- Si el administrador opera directo en consola, quedará nulo
    END;

    IF (TG_OP = 'DELETE') THEN
        INSERT INTO auditoria.bitacora_eventos 
            (nombre_tabla, tipo_operacion, id_usuario_app, estado_anterior, estado_nuevo)
        VALUES 
            (TG_TABLE_NAME, TG_OP, v_user_id, row_to_json(OLD)::JSONB, NULL);
        RETURN OLD;
        
    ELSIF (TG_OP = 'UPDATE') THEN
        -- Optimización: Solo registrar si realmente hubo cambios
        IF (OLD IS DISTINCT FROM NEW) THEN
            INSERT INTO auditoria.bitacora_eventos 
                (nombre_tabla, tipo_operacion, id_usuario_app, estado_anterior, estado_nuevo)
            VALUES 
                (TG_TABLE_NAME, TG_OP, v_user_id, row_to_json(OLD)::JSONB, row_to_json(NEW)::JSONB);
        END IF;
        RETURN NEW;
        
    ELSIF (TG_OP = 'INSERT') THEN
        INSERT INTO auditoria.bitacora_eventos 
            (nombre_tabla, tipo_operacion, id_usuario_app, estado_anterior, estado_nuevo)
        VALUES 
            (TG_TABLE_NAME, TG_OP, v_user_id, NULL, row_to_json(NEW)::JSONB);
        RETURN NEW;
    END IF;
    
    RETURN NULL;
END;
$$;


ALTER FUNCTION auditoria.fn_registrar_auditoria() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bitacora_eventos; Type: TABLE; Schema: auditoria; Owner: postgres
--

CREATE TABLE auditoria.bitacora_eventos (
    id_evento uuid DEFAULT gen_random_uuid() NOT NULL,
    nombre_tabla character varying(100) NOT NULL,
    tipo_operacion character varying(10) NOT NULL,
    id_usuario_app uuid,
    estado_anterior jsonb,
    estado_nuevo jsonb,
    fecha_evento timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT bitacora_eventos_tipo_operacion_check CHECK (((tipo_operacion)::text = ANY (ARRAY[('INSERT'::character varying)::text, ('UPDATE'::character varying)::text, ('DELETE'::character varying)::text])))
);


ALTER TABLE auditoria.bitacora_eventos OWNER TO postgres;

--
-- Name: bitacora_eventos bitacora_eventos_pkey; Type: CONSTRAINT; Schema: auditoria; Owner: postgres
--

ALTER TABLE ONLY auditoria.bitacora_eventos
    ADD CONSTRAINT bitacora_eventos_pkey PRIMARY KEY (id_evento);


--
-- Name: bitacora_eventos trg_proteger_bitacora; Type: TRIGGER; Schema: auditoria; Owner: postgres
--

CREATE TRIGGER trg_proteger_bitacora BEFORE DELETE OR UPDATE ON auditoria.bitacora_eventos FOR EACH ROW EXECUTE FUNCTION auditoria.fn_bloquear_modificacion_auditoria();


--
-- Name: SCHEMA auditoria; Type: ACL; Schema: -; Owner: postgres
--

GRANT USAGE ON SCHEMA auditoria TO app_backend;
GRANT USAGE ON SCHEMA auditoria TO app_auditor;


--
-- Name: TABLE bitacora_eventos; Type: ACL; Schema: auditoria; Owner: postgres
--

GRANT SELECT,INSERT ON TABLE auditoria.bitacora_eventos TO app_backend;
GRANT SELECT ON TABLE auditoria.bitacora_eventos TO app_auditor;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: auditoria; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA auditoria GRANT SELECT,INSERT ON TABLES TO app_backend;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA auditoria GRANT SELECT ON TABLES TO app_auditor;


--
-- PostgreSQL database dump complete
--

