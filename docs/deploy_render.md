# Despliegue a Render — CRM-Granos-MX

**Audiencia:** operador del proyecto (Carlos) y cualquier ingeniero que herede el proyecto.
**Tiempo total estimado:** 30–40 min para primer deploy desde cero.
**Costo mensual estimado:** ~$14 USD (Web starter $7 + Postgres starter $7).

---

## 1. Pre-requisitos

- [ ] Cuenta en Render (https://render.com).
- [ ] Cuenta en GitHub donde vive el repo.
- [ ] Tokens listos (los pegarás en el dashboard de Render):
  - `INEGI_DENUE_TOKEN` (gratis en https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx).
  - `GOOGLE_PLACES_API_KEY` (Google Cloud Console → APIs → credentials).
  - `SEED_ADMIN_PASSWORD` (genera local con `python -c "import secrets; print(secrets.token_urlsafe(20))"`).

---

## 2. Subir código a GitHub

```bash
cd CRM-Granos-MX
git remote add origin https://github.com/<tu-org>/crm-granos-mx.git
git push -u origin main
```

⚠️ **Antes de pushear** verifica que `.env` esté en `.gitignore`. Si subiste secretos por error: rota inmediatamente el token en el panel del proveedor.

---

## 3. Crear el blueprint en Render

1. **Render dashboard → New → Blueprint**.
2. Conectar el repo de GitHub.
3. Render lee `render.yaml` automáticamente y propone:
   - 1 Web Service (`crm-granos-mx`).
   - 1 PostgreSQL (`crm-granos-mx-db`).
   - 1 Cron job (`crm-cron-sat-69b`, mensual).
4. Click **Apply**.
5. Render genera automáticamente:
   - `SECRET_KEY`, `JWT_SECRET_KEY`, `RECOVERY_MASTER_KEY` (256 bits cada uno).
   - `DATABASE_URL` (apunta al Postgres recién creado).

---

## 4. Configurar secrets manuales

Tras crear el servicio, ve a **Render → crm-granos-mx → Environment** y completa los que tienen `sync: false`:

| Variable | Valor | Notas |
|---|---|---|
| `INEGI_DENUE_TOKEN` | el token UUID | Compartido con el cron job |
| `GOOGLE_PLACES_API_KEY` | la API key | Restringida a Places API (New) en Google Cloud |
| `SEED_ADMIN_PASSWORD` | password fuerte | Solo se usa en primer deploy. Cambiar tras login |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | (opcional) | Para Fase 9 — recovery por email |

⚠️ **`MONTHLY_BUDGET_USD`** ya viene en $100. Si quieres bajar el límite del circuit breaker, edita aquí.

---

## 5. Primer deploy

1. Tras Apply, Render arranca el build automáticamente.
2. **Build phase:** `pip install -e .` → tarda ~2-3 min (geopandas y deps geo son pesadas).
3. **PreDeploy phase:** corre `alembic upgrade head && python scripts/seed_admin.py`:
   - Crea las extensiones `postgis` y `pg_trgm` (la baseline migration tiene `CREATE EXTENSION IF NOT EXISTS`).
   - Crea las 14 tablas + 4 vistas + 6 índices GIST/GIN.
   - Siembra el catálogo `_columnas_pii` con 21 columnas.
   - Crea el usuario admin con el password de `SEED_ADMIN_PASSWORD`.
4. **Start phase:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --workers 2`.
5. Render valida `/health` → si responde 200, marca deploy como **Live**.

URL pública: `https://crm-granos-mx.onrender.com` (depende del nombre que Render asigne).

---

## 6. Smoke post-deploy

```bash
# Health
curl https://crm-granos-mx.onrender.com/health
# {"status":"ok","version":"0.1.0","env":"production"}

# Login (admin / SEED_ADMIN_PASSWORD)
curl -c /tmp/cookies.txt -X POST https://crm-granos-mx.onrender.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<el-password>"}'

# Ver dashboard en navegador
open https://crm-granos-mx.onrender.com/login
```

✅ Esperado tras login:
- Dashboard con 0 prospectos (la base está vacía — pendiente cargar data).
- KPIs en cero, tablas vacías, mapa sin marcadores.

---

## 7. Cargar data en producción

La data NO se carga automáticamente. Tras primer deploy, ejecuta los pipelines de ingesta uno a uno desde **Render → crm-granos-mx → Shell**:

```bash
# 1. Ingesta DENUE — 16 entidades, ~5 min, 136K establecimientos
python -m src.ingestion.cli --full

# 2. SAT 69-B (mensual — el cron lo hará automático luego)
python -m src.ingestion.cli --descargar-69b
python -m src.ingestion.cli --cruzar-69b

# 3. INEGI Indicadores (seed YAML)
python -m src.ingestion.cli --cargar-indicadores

# 4. Detectar cadenas
python -m src.ingestion.cli --detectar-cadenas

# 5. Enriquecimiento Google Places — CONFIRMA presupuesto antes de correr
python -m src.ingestion.cli --enriquecer --max-total 1000
python -m src.ingestion.cli --gasto

# 6. Aplicar etiquetas (CONAFAB / PECUARIO_GRANDE / HARINERO_INDUSTRIAL)
python -m src.ingestion.cli --aplicar-etiquetas

# 7. Calcular scores + segmentación A/B/C
python -m src.ingestion.cli --calcular-scores

# 8. Asignar vendedores (requiere registrar vendedores primero)
python -m src.ingestion.cli --asignar-vendedores
```

⚠️ El plan **starter** tiene 1 GB de storage. Con 136K establecimientos + enriquecimiento + interacciones cabe holgado, pero monitorea uso con `\dt+` desde psql.

---

## 8. Cron jobs

`render.yaml` incluye un cron mensual `crm-cron-sat-69b` que corre el día 1 a las 9:00 UTC (3 AM CDMX):

```bash
python -m src.ingestion.cli --descargar-69b && python -m src.ingestion.cli --cruzar-69b
```

Para agregar más cron jobs (ARCO marcar vencidas, refresh indicadores, etc.) edita `render.yaml` y push a `main`.

---

## 9. Backups

**Render Postgres starter** incluye backups diarios automáticos (retenidos 7 días).
Para backups manuales antes de migraciones grandes:

```bash
# Desde Render → crm-granos-mx-db → Backups → "Trigger Backup"
# O desde tu máquina local:
pg_dump "$DATABASE_URL_FROM_RENDER_DASHBOARD" > backup-2026-MM-DD.sql
```

---

## 10. Variables que cambian de development → production

| Variable | Dev | Prod |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` |
| `DATABASE_URL` | localhost | Render-managed |
| Cookie `crm_token` | `Secure=False` | `Secure=True` (HTTPS only) |
| `CORS_ORIGINS` | `localhost:5173,8000` | URL pública Render |
| Logs | console + file | console only (Render captura stdout) |

El código en `src/core/config.py` y `src/api/routes/auth_routes.py` ya respeta estas diferencias automáticamente vía `settings.is_production`.

---

## 11. Troubleshooting

### "extension postgis is not available"
El plan **starter** SÍ soporta postgis. Si aparece el error, revisa que la región sea Oregon o las disponibles. Si tu DB está en otra región sin postgis, recrea la DB.

### "DATABASE_URL invalid format"
Render entrega `postgres://...`. El validator en `src/core/config.py:_normalize_db_url` lo traduce a `postgresql+psycopg://...`. Si ves el error, revisa que la dep `psycopg[binary]` esté instalada.

### Build muy lento (>5 min)
geopandas + shapely + numpy + pandas son ~150 MB de wheels. Render cachea entre deploys, así que el primero es el lento. Si el build falla por timeout, considera mover a plan **standard** (más CPU) o quita geopandas del path crítico.

### "alembic upgrade head" falla con "already exists"
Pasaba si subiste un dump con `CREATE TABLE` y luego corres alembic. Solución: o haces `alembic stamp head` para marcar la DB como up-to-date sin correr migraciones, o limpias y dejas que alembic cree todo desde cero.

### Logs
Render → crm-granos-mx → Logs (live tail). Loguru imprime a stdout, así que se ve todo.

---

## 12. Pendientes operativos LFPDPPP antes de uso real con prospectos

Tomado de `docs/compliance_lfpdppp.md`. Estos NO los hace este deploy:

1. Asesor legal revisa los avisos de privacidad (`docs/aviso_privacidad_*.md`).
2. Configurar `datos@intergranel.mx` (mailbox de derechos ARCO).
3. Designar oficialmente al Responsable de Protección de Datos Personales.
4. Capacitar al equipo de ventas en captura de PII.
5. Publicar `aviso_privacidad_integral.md` en el sitio web público (intergranel.mx).
6. Backups del `compliance_log` en almacenamiento independiente (no solo Render).
7. Revisar contratos de tratamiento con Google y Render.

Hasta cumplir esos 7 puntos, **NO se contacta a prospectos reales** desde el sistema.
