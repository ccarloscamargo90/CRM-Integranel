"""api — endpoints FastAPI.

Módulos planeados (Fase 8):
- routes.py       → /prospectos, /prospectos/{id}, /rutas, /prospectos/{id}/contacto
- auth.py         → login, JWT, recuperación, roles admin/vendedor/jefe
- dependencies.py → get_db, get_current_user, require_role(...)
- main.py         → app FastAPI, CORS, lifespan, mount

Autenticación: JWT en cookie httpOnly + 3 roles.
Cada endpoint que toca PII registra en `compliance_log` automáticamente
vía dependencia `audit_pii_access`.
"""
