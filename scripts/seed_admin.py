"""Crea un usuario admin inicial. Idempotente: si ya existe lo deja.

Uso:
    python scripts/seed_admin.py [username] [password]

Si no se pasan args, usa defaults para desarrollo (usuario=admin, password=changeme).
NO usar defaults en producción — Render debe tener vars SEED_ADMIN_USER y
SEED_ADMIN_PASSWORD en el environment.
"""

from __future__ import annotations

import os
import secrets
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(".env")

    from src.api.auth import hash_password
    from src.core.db import SessionLocal
    from src.core.models import Usuario

    username = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("SEED_ADMIN_USER", "admin")
    )
    password = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.getenv("SEED_ADMIN_PASSWORD", "")
    )

    if not password:
        # Generar password aleatorio seguro y mostrarlo
        password = secrets.token_urlsafe(16)
        print(f"⚠️  Password no proporcionado. Generado: {password}")
        print("⚠️  GUÁRDALO AHORA — no se mostrará otra vez.")

    with SessionLocal() as db:
        existente = db.query(Usuario).filter(Usuario.username == username).first()
        if existente:
            # Si pasaron password explícito, lo actualizamos. Sino solo informamos.
            if len(sys.argv) > 2:
                existente.password_hash = hash_password(password)
                db.commit()
                print(f"✓ Usuario '{username}' actualizado con nuevo password.")
            else:
                print(f"✓ Usuario '{username}' ya existe (no se modificó).")
            return 0

        nuevo = Usuario(
            username=username,
            password_hash=hash_password(password),
            nombre=f"Admin ({username})",
            email=None,
            rol="admin",
            activo=True,
        )
        db.add(nuevo)
        db.commit()
        print(f"✓ Usuario admin '{username}' creado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
