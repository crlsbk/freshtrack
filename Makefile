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

.PHONY: help setup venv db bootstrap etl app demo verify smoke test up infra down clean

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
	@echo "  make smoke      Recorre todas las pantallas con los 7 roles"
	@echo "  make test       smoke + demo + verify"
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
	$(PYBIN) -m pip install -r requirements.txt
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

test: smoke demo verify

up: setup
	docker compose up -d

# Levanta unicamente los motores de datos (sin la aplicacion). Util para correr
# Flask fuera de Docker contra los contenedores.
infra: setup
	docker compose up -d postgres mongo redis

down:
	docker compose down

clean:
	docker compose down -v
