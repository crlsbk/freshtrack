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
-- Name: operacion; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA operacion;


ALTER SCHEMA operacion OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: existencia; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.existencia (
    id_existencia uuid DEFAULT gen_random_uuid() NOT NULL,
    id_lote uuid NOT NULL,
    id_locacion integer NOT NULL,
    cantidad_disponible numeric(10,2) NOT NULL,
    cantidad_reservada numeric(10,2) DEFAULT 0 NOT NULL,
    CONSTRAINT chk_cantidad_disponible CHECK ((cantidad_disponible >= (0)::numeric)),
    CONSTRAINT chk_cantidad_reservada CHECK ((cantidad_reservada >= (0)::numeric))
);


ALTER TABLE operacion.existencia OWNER TO postgres;

--
-- Name: locacion; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.locacion (
    id_locacion integer NOT NULL,
    tipo_locacion character varying(20) NOT NULL,
    nombre character varying(100) NOT NULL,
    CONSTRAINT chk_tipo_locacion CHECK (((tipo_locacion)::text = ANY (ARRAY[('Tienda'::character varying)::text, ('CEDIS'::character varying)::text])))
);


ALTER TABLE operacion.locacion OWNER TO postgres;

--
-- Name: locacion_id_locacion_seq; Type: SEQUENCE; Schema: operacion; Owner: postgres
--

ALTER TABLE operacion.locacion ALTER COLUMN id_locacion ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME operacion.locacion_id_locacion_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: lote; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.lote (
    id_lote uuid DEFAULT gen_random_uuid() NOT NULL,
    id_sku integer NOT NULL,
    id_proveedor integer NOT NULL,
    codigo_lote_prov character varying(50) NOT NULL,
    fecha_caducidad date NOT NULL
);


ALTER TABLE operacion.lote OWNER TO postgres;

--
-- Name: merma; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.merma (
    id_merma uuid DEFAULT gen_random_uuid() NOT NULL,
    id_lote uuid NOT NULL,
    id_usuario uuid NOT NULL,
    cantidad numeric(10,2) NOT NULL,
    causa_merma character varying(30) NOT NULL,
    fecha_registro timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_cantidad_merma CHECK ((cantidad > (0)::numeric))
);


ALTER TABLE operacion.merma OWNER TO postgres;

--
-- Name: producto; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.producto (
    id_sku integer NOT NULL,
    codigo_gtin character(14) NOT NULL,
    nombre character varying(150) NOT NULL,
    vida_util_estandar integer NOT NULL,
    CONSTRAINT chk_vida_util CHECK ((vida_util_estandar > 0))
);


ALTER TABLE operacion.producto OWNER TO postgres;

--
-- Name: producto_id_sku_seq; Type: SEQUENCE; Schema: operacion; Owner: postgres
--

ALTER TABLE operacion.producto ALTER COLUMN id_sku ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME operacion.producto_id_sku_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: proveedor; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.proveedor (
    id_proveedor integer NOT NULL,
    rfc character(13) NOT NULL,
    razon_social character varying(150) NOT NULL,
    lead_time_dias integer NOT NULL,
    CONSTRAINT chk_lead_time CHECK ((lead_time_dias >= 0))
);


ALTER TABLE operacion.proveedor OWNER TO postgres;

--
-- Name: proveedor_id_proveedor_seq; Type: SEQUENCE; Schema: operacion; Owner: postgres
--

ALTER TABLE operacion.proveedor ALTER COLUMN id_proveedor ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME operacion.proveedor_id_proveedor_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: rol; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.rol (
    id_rol integer NOT NULL,
    nombre_rol character varying(50) NOT NULL
);


ALTER TABLE operacion.rol OWNER TO postgres;

--
-- Name: rol_id_rol_seq; Type: SEQUENCE; Schema: operacion; Owner: postgres
--

ALTER TABLE operacion.rol ALTER COLUMN id_rol ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME operacion.rol_id_rol_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: usuario; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.usuario (
    id_usuario uuid DEFAULT gen_random_uuid() NOT NULL,
    id_rol integer NOT NULL,
    id_locacion integer NOT NULL,
    nombre_completo character varying(150) NOT NULL,
    estado_activo boolean DEFAULT true NOT NULL,
    email character varying(255) UNIQUE,
    password_hash text
);


ALTER TABLE operacion.usuario OWNER TO postgres;

--
-- Name: venta_detalle; Type: TABLE; Schema: operacion; Owner: postgres
--

CREATE TABLE operacion.venta_detalle (
    id_venta uuid DEFAULT gen_random_uuid() NOT NULL,
    id_lote uuid NOT NULL,
    id_locacion integer NOT NULL,
    cantidad numeric(10,2) NOT NULL,
    fecha_transaccion timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_cantidad_venta CHECK ((cantidad > (0)::numeric))
);


ALTER TABLE operacion.venta_detalle OWNER TO postgres;

--
-- Name: existencia pk_existencia; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.existencia
    ADD CONSTRAINT pk_existencia PRIMARY KEY (id_existencia);


--
-- Name: locacion pk_locacion; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.locacion
    ADD CONSTRAINT pk_locacion PRIMARY KEY (id_locacion);


--
-- Name: lote pk_lote; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.lote
    ADD CONSTRAINT pk_lote PRIMARY KEY (id_lote);


--
-- Name: merma pk_merma; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.merma
    ADD CONSTRAINT pk_merma PRIMARY KEY (id_merma);


--
-- Name: producto pk_producto; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.producto
    ADD CONSTRAINT pk_producto PRIMARY KEY (id_sku);


--
-- Name: proveedor pk_proveedor; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.proveedor
    ADD CONSTRAINT pk_proveedor PRIMARY KEY (id_proveedor);


--
-- Name: rol pk_rol; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.rol
    ADD CONSTRAINT pk_rol PRIMARY KEY (id_rol);


--
-- Name: usuario pk_usuario; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.usuario
    ADD CONSTRAINT pk_usuario PRIMARY KEY (id_usuario);


--
-- Name: venta_detalle pk_venta_detalle; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.venta_detalle
    ADD CONSTRAINT pk_venta_detalle PRIMARY KEY (id_venta);


--
-- Name: producto uq_codigo_gtin; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.producto
    ADD CONSTRAINT uq_codigo_gtin UNIQUE (codigo_gtin);


--
-- Name: rol uq_nombre_rol; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.rol
    ADD CONSTRAINT uq_nombre_rol UNIQUE (nombre_rol);


--
-- Name: proveedor uq_rfc; Type: CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.proveedor
    ADD CONSTRAINT uq_rfc UNIQUE (rfc);


--
-- Name: existencia trg_auditoria_existencia; Type: TRIGGER; Schema: operacion; Owner: postgres
--

CREATE TRIGGER trg_auditoria_existencia AFTER INSERT OR DELETE OR UPDATE ON operacion.existencia FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria();


--
-- Name: lote trg_auditoria_lote; Type: TRIGGER; Schema: operacion; Owner: postgres
--

CREATE TRIGGER trg_auditoria_lote AFTER INSERT OR DELETE OR UPDATE ON operacion.lote FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria();


--
-- Name: merma trg_auditoria_merma; Type: TRIGGER; Schema: operacion; Owner: postgres
--

CREATE TRIGGER trg_auditoria_merma AFTER INSERT OR DELETE OR UPDATE ON operacion.merma FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria();


--
-- Name: venta_detalle trg_auditoria_venta; Type: TRIGGER; Schema: operacion; Owner: postgres
--

CREATE TRIGGER trg_auditoria_venta AFTER INSERT OR DELETE OR UPDATE ON operacion.venta_detalle FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria();


--
-- Name: existencia fk_existencia_locacion; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.existencia
    ADD CONSTRAINT fk_existencia_locacion FOREIGN KEY (id_locacion) REFERENCES operacion.locacion(id_locacion) ON DELETE RESTRICT;


--
-- Name: existencia fk_existencia_lote; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.existencia
    ADD CONSTRAINT fk_existencia_lote FOREIGN KEY (id_lote) REFERENCES operacion.lote(id_lote) ON DELETE RESTRICT;


--
-- Name: lote fk_lote_producto; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.lote
    ADD CONSTRAINT fk_lote_producto FOREIGN KEY (id_sku) REFERENCES operacion.producto(id_sku) ON DELETE RESTRICT;


--
-- Name: lote fk_lote_proveedor; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.lote
    ADD CONSTRAINT fk_lote_proveedor FOREIGN KEY (id_proveedor) REFERENCES operacion.proveedor(id_proveedor) ON DELETE RESTRICT;


--
-- Name: merma fk_merma_lote; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.merma
    ADD CONSTRAINT fk_merma_lote FOREIGN KEY (id_lote) REFERENCES operacion.lote(id_lote) ON DELETE RESTRICT;


--
-- Name: merma fk_merma_usuario; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.merma
    ADD CONSTRAINT fk_merma_usuario FOREIGN KEY (id_usuario) REFERENCES operacion.usuario(id_usuario) ON DELETE RESTRICT;


--
-- Name: usuario fk_usuario_locacion; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.usuario
    ADD CONSTRAINT fk_usuario_locacion FOREIGN KEY (id_locacion) REFERENCES operacion.locacion(id_locacion) ON DELETE RESTRICT;


--
-- Name: usuario fk_usuario_rol; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.usuario
    ADD CONSTRAINT fk_usuario_rol FOREIGN KEY (id_rol) REFERENCES operacion.rol(id_rol) ON DELETE RESTRICT;


--
-- Name: venta_detalle fk_venta_locacion; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.venta_detalle
    ADD CONSTRAINT fk_venta_locacion FOREIGN KEY (id_locacion) REFERENCES operacion.locacion(id_locacion) ON DELETE RESTRICT;


--
-- Name: venta_detalle fk_venta_lote; Type: FK CONSTRAINT; Schema: operacion; Owner: postgres
--

ALTER TABLE ONLY operacion.venta_detalle
    ADD CONSTRAINT fk_venta_lote FOREIGN KEY (id_lote) REFERENCES operacion.lote(id_lote) ON DELETE RESTRICT;


--
-- Name: SCHEMA operacion; Type: ACL; Schema: -; Owner: postgres
--

GRANT USAGE ON SCHEMA operacion TO app_backend;
GRANT USAGE ON SCHEMA operacion TO app_auditor;


--
-- Name: TABLE existencia; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.existencia TO app_backend;
GRANT SELECT ON TABLE operacion.existencia TO app_auditor;


--
-- Name: TABLE locacion; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.locacion TO app_backend;
GRANT SELECT ON TABLE operacion.locacion TO app_auditor;


--
-- Name: SEQUENCE locacion_id_locacion_seq; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON SEQUENCE operacion.locacion_id_locacion_seq TO app_backend;


--
-- Name: TABLE lote; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.lote TO app_backend;
GRANT SELECT ON TABLE operacion.lote TO app_auditor;


--
-- Name: TABLE merma; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.merma TO app_backend;
GRANT SELECT ON TABLE operacion.merma TO app_auditor;


--
-- Name: TABLE producto; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.producto TO app_backend;
GRANT SELECT ON TABLE operacion.producto TO app_auditor;


--
-- Name: SEQUENCE producto_id_sku_seq; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON SEQUENCE operacion.producto_id_sku_seq TO app_backend;


--
-- Name: TABLE proveedor; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.proveedor TO app_backend;
GRANT SELECT ON TABLE operacion.proveedor TO app_auditor;


--
-- Name: SEQUENCE proveedor_id_proveedor_seq; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON SEQUENCE operacion.proveedor_id_proveedor_seq TO app_backend;


--
-- Name: TABLE rol; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.rol TO app_backend;
GRANT SELECT ON TABLE operacion.rol TO app_auditor;


--
-- Name: SEQUENCE rol_id_rol_seq; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON SEQUENCE operacion.rol_id_rol_seq TO app_backend;


--
-- Name: TABLE usuario; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.usuario TO app_backend;
GRANT SELECT ON TABLE operacion.usuario TO app_auditor;


--
-- Name: TABLE venta_detalle; Type: ACL; Schema: operacion; Owner: postgres
--

GRANT ALL ON TABLE operacion.venta_detalle TO app_backend;
GRANT SELECT ON TABLE operacion.venta_detalle TO app_auditor;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: operacion; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA operacion GRANT ALL ON TABLES TO app_backend;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA operacion GRANT SELECT ON TABLES TO app_auditor;


--
-- PostgreSQL database dump complete
--

