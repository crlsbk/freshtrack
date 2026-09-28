"""Prueba de humo: recorre todas las pantallas con cada rol y reporta el HTTP."""

from __future__ import annotations

import os
import sys

RAIZ = r"C:\VSCode\ProyectoIAC"
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.navegacion import VISTAS_POR_ROL, endpoint_de

CUENTAS = {
    "admin": ("admin@freshtrack.mx", "Admin2026!"),
    "buyer": ("buyer@freshtrack.mx", "Compras2026!"),
    "planner": ("planner@freshtrack.mx", "Plan2026!"),
    "store_manager": ("gerente@freshtrack.mx", "Tienda2026!"),
    "warehouse": ("almacen@freshtrack.mx", "Almacen2026!"),
    "supplier": ("proveedor@freshtrack.mx", "Proveedor2026!"),
    "auditor": ("auditor@freshtrack.mx", "Auditor2026!"),
}

app = create_app()
app.config["TESTING"] = True

rutas = {}
for vista in {v for vs in VISTAS_POR_ROL.values() for v in vs}:
    ep = endpoint_de(vista)
    if ep:
        rutas[vista] = ep

fallos = []
total = 0

with app.test_client() as c:
    for rol, (email, pwd) in CUENTAS.items():
        r = c.post("/login", data={"email": email, "password": pwd}, follow_redirects=False)
        if r.status_code != 302:
            fallos.append(f"{rol}: el login no redirigió ({r.status_code})")
            continue
        print(f"\n=== {rol} ===")
        for vista in sorted(VISTAS_POR_ROL[rol]):
            ep = rutas.get(vista)
            if not ep:
                continue
            url = app.url_map.bind("localhost").build(ep)
            resp = c.get(url)
            total += 1
            marca = "OK  " if resp.status_code == 200 else "FALLO"
            if resp.status_code != 200:
                fallos.append(f"{rol} → {url} = {resp.status_code}")
            print(f"   [{marca}] {url:<34} {resp.status_code}")
        c.get("/logout")

    # La landing es pública y no debe mandar al login.
    resp = c.get("/")
    total += 1
    cuerpo = resp.get_data(as_text=True)
    ok = (
        resp.status_code == 200
        and "FreshTrack" in cuerpo
        and 'name="password"' not in cuerpo  # no es la pantalla de login
    )
    print(f"\n[{'OK  ' if ok else 'FALLO'}] landing pública / → {resp.status_code}")
    if not ok:
        fallos.append(f"la landing / devolvió {resp.status_code}")

print(f"\nPantallas probadas: {total}")
if fallos:
    print(f"FALLOS ({len(fallos)}):")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todas las pantallas responden 200 con el rol que tiene permiso.")
