# Setup de PostgreSQL local con Postgres.app

Esta guía es para instalar PostgreSQL 16 + PostGIS en tu Mac sin Docker, sin Homebrew, sin terminal complicada. Tiempo estimado: **5 minutos**.

---

## ¿Por qué Postgres.app y no Docker?

Postgres.app es una aplicación nativa de macOS que empaqueta PostgreSQL + PostGIS + utilidades CLI en un solo `.app` que arrastras a `Applications`. No requiere instalación, no requiere terminal para arrancarlo, no consume memoria cuando está cerrado.

Para producción usaremos Render (con su Postgres administrado y PostGIS habilitado). Postgres.app sólo es para desarrollo local.

---

## Instalación paso a paso

### 1. Descarga
Ve a https://postgresapp.com/ y haz clic en **Download**. Te baja un archivo `Postgres-2.7.x-16,17.dmg` (~250 MB).

### 2. Instala
Abre el `.dmg`. Verás una ventana con un ícono de elefante azul (Postgres.app) y un acceso directo a la carpeta Applications. **Arrastra el ícono a Applications**.

### 3. Primera vez
Abre Launchpad → busca "Postgres" → clic. La primera vez te aparecerá un aviso de seguridad de macOS ("¿Estás seguro de abrir esta aplicación descargada de internet?"). Confirma "Abrir".

Postgres.app se abre con una ventana mostrando:
- Un servidor llamado **"PostgreSQL 17"** (o la versión más reciente disponible)
- Un botón verde **"Initialize"** o **"Start"**

Haz clic en **Initialize / Start**. En ~10 segundos el servidor está corriendo (verás un cuadrito verde junto al nombre).

### 4. Configurar el PATH para CLI

Para que comandos como `createdb`, `psql`, `pg_isready` funcionen desde la terminal, abre Terminal.app y corre:

```bash
sudo mkdir -p /etc/paths.d &&
echo /Applications/Postgres.app/Contents/Versions/latest/bin | sudo tee /etc/paths.d/postgresapp
```

Te pedirá tu contraseña de Mac. Después **cierra la terminal y abre una nueva** para que tome el cambio.

### 5. Verificar

En una terminal nueva, corre:

```bash
psql --version
```

Deberías ver algo como `psql (PostgreSQL) 17.x` o `16.x`. Si dice "command not found", el PATH no se aplicó — cierra TODAS las terminales y abre una nueva.

### 6. Crear la base de datos del proyecto

```bash
createdb crm_granos_mx
psql crm_granos_mx -c "CREATE EXTENSION postgis;"
psql crm_granos_mx -c "SELECT PostGIS_Version();"
```

La última línea debe imprimir algo como `3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1`.

✅ **Listo.** Ya tienes PostgreSQL local con PostGIS.

---

## Conexión desde el proyecto

En `.env` la variable ya está configurada como:

```
DATABASE_URL=postgresql+psycopg://carlosacamargo@localhost:5432/crm_granos_mx
```

Postgres.app crea por default un usuario con tu nombre de usuario macOS y sin contraseña en localhost. Esto sólo funciona en local — Render usa usuarios y contraseñas reales.

---

## Apagar / encender Postgres.app

- Cierra Postgres.app (cmd+Q) → el servidor se detiene.
- Abre Postgres.app → el servidor arranca solo en ~3 segundos.
- Si quieres que arranque solo al iniciar el Mac: Postgres.app → Preferences → "Open at Login".

---

## Si algo falla

| Síntoma | Causa probable | Solución |
|---|---|---|
| `psql: command not found` | PATH no se aplicó | Cierra todas las terminales, abre una nueva |
| `createdb: error: connection ... refused` | Postgres.app no está corriendo | Abre la app y dale Start |
| `ERROR: extension "postgis" is not available` | Versión de Postgres.app sin PostGIS | Re-descarga la versión "Postgres.app with all extensions" desde la web |
| `password authentication failed` | Estás conectándote a otra instancia | Verifica que tu DATABASE_URL apunte a `localhost:5432` |

---

## Apéndice: GUI opcional para inspeccionar la DB

Si prefieres ver la BD con UI (en lugar de `psql`), descarga:
- **TablePlus** (gratis con limitaciones, https://tableplus.com/) — recomendado
- **DBeaver Community** (gratis ilimitado, https://dbeaver.io/)
- **pgAdmin** (gratis, oficial de Postgres, https://www.pgadmin.org/)

Conexión:
- Host: `localhost`
- Puerto: `5432`
- DB: `crm_granos_mx`
- Usuario: tu usuario macOS
- Password: (vacío)
