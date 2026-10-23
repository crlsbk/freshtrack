# =============================================================================
# FreshTrack — atajos de operación
#
# Flujo desde cero:
#     make setup      # crea .env a partir de env.example
#     make bootstrap  # crea la base, los roles, los esquemas y los datos base
#     make etl        # carga 180 días de historia operativa
#     make app        # levanta Flask en http://127.0.0.1:5000
#
# Flujo con Docker (hace 1-3 solo, dentro del contenedor de PostgreSQL):
#     make up
# =============================================================================

PYTHON ?= python
VENV   ?= .venv
ifeq ($(OS),Windows_NT)
	PYBIN := $(VENV)/Scripts/python.exe
else
	PYBIN := $(VENV)/bin/python
endif

# Accion para `make db` (start | stop | status | restart). Por defecto, arrancar.
ACCION ?= start

.PHONY: help setup venv db bootstrap etl app demo verify smoke test test-unit test-integration smoke-http services up infra down clean verify-polyglot verify-mongo verify-redis verify-microservices verify-security check-planeador check-servicios

help:
	@echo "FreshTrack — objetivos disponibles:"
	@echo "  make setup      Copia env.example a .env"
	@echo "  make venv       Crea .venv e instala requirements.txt"
	@echo "  make db         Arranca el PostgreSQL portable (ver ACCION abajo)"
	@echo "  make bootstrap  Crea la base, roles, esquemas y datos base"
	@echo "  make etl        Carga la historia operativa (180 dias)"
	@echo "  make app        Levanta la aplicacion Flask"
	@echo "  make demo       Ejecuta el escenario extremo a extremo"
	@echo "  make verify     Comprueba la persistencia en un proceso nuevo"
	@echo "  make verify-polyglot Comprueba PostgreSQL, Redis, Mongo y Sagas"
	@echo "  make verify-mongo Comprueba las 7 operaciones documentales en MongoDB"
	@echo "  make verify-microservices Comprueba los 8 microservicios contenerizados (JSON/XML/Saga)"
	@echo "  make smoke      Recorre todas las pantallas con los 7 roles"
	@echo "  make test       Pruebas unitarias + de integración (pytest)"
	@echo "  make test-unit  Solo pruebas unitarias (no requieren bases de datos)"
	@echo "  make smoke-http Prueba HTTP contra los contenedores levantados"
	@echo "  make check-servicios Barrido de los 8 microservicios: JSON/XML, saga, XSD y docker logs"
	@echo "  make check-planeador Flujo del planeador por HTTP real: JSON/XML, JWT y Redis (-v con CHECK_ARGS=-v)"
	@echo "  make services   Levanta los 8 microservicios fuera de Docker (puertos 5001-5008)"
	@echo "  make verify-all smoke + verify-* + demo + verify (scripts de demostración)"
	@echo "  make infra      Levanta solo PostgreSQL, MongoDB y Redis"
	@echo "  make up/down/clean  Docker Compose (los 3 motores + la app)"
	@echo ""
	@echo "  make db ACCION=stop|status|restart   Controla el PostgreSQL portable"

setup:
	@test -f .env || cp env.example .env
	@echo ".env listo. Ajusta las claves antes de continuar."

venv:
	$(PYTHON) -m venv $(VENV)
	$(PYBIN) -m pip install --upgrade pip
	$(PYBIN) -m pip install -r requirements-dev.txt
	@echo "Entorno virtual listo en $(VENV)."

# Arranca/para el PostgreSQL portable. Por defecto arranca. El puerto se lee de
# DATABASE_URL, asi que el servidor y la aplicacion no pueden discrepar.
db:
	@bash scripts/start_db.sh $(ACCION)

bootstrap:
	$(PYBIN) scripts/bootstrap_db.py

etl:
	$(PYBIN) scripts/ETL.py

app:
	$(PYBIN) run.py

demo:
	$(PYBIN) scripts/demo_avance2.py --escenario

verify:
	$(PYBIN) scripts/demo_avance2.py --verificar

smoke:
	$(PYBIN) scripts/smoke_rutas.py

verify-polyglot:
	$(PYBIN) scripts/verify_polyglot.py

verify-mongo:
	$(PYBIN) scripts/verify_mongo.py

verify-redis:
	$(PYBIN) scripts/verify_redis.py

verify-microservices:
	$(PYBIN) scripts/verify_all_microservices.py

verify-security:
	$(PYBIN) scripts/verify_security.py

test: test-unit test-integration

test-unit:
	$(PYBIN) -m pytest tests/unit -v

test-integration:
	$(PYBIN) -m pytest tests/integration -v

check-planeador:
	$(PYTHON) scripts/check_planeador.py $(CHECK_ARGS)

check-servicios:
	$(PYTHON) scripts/check_servicios.py $(CHECK_ARGS)

smoke-http:
	$(PYBIN) scripts/smoke_http.py

services:
	@for s in auth catalog inventory commercial asn planning alerts audit; do 		$(PYBIN) app/services/$${s}_service/app.py & 	done; wait

verify-all: smoke verify-polyglot verify-mongo verify-redis verify-microservices verify-security demo verify

up: setup
	docker compose up -d --build --wait

# Levanta unicamente los motores de datos (sin la aplicacion). Util para correr
# Flask fuera de Docker contra los contenedores.
infra: setup
	docker compose up -d postgres mongo redis

down:
	docker compose down

clean:
	docker compose down -v
