# Desarrollo local (Ubuntu / WSL2)

Requisitos: Python 3.12 con venv y Poetry 2.x disponibles. No se requieren
PostgreSQL, Redis, Docker ni credenciales para ejecutar esta suite.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
poetry install --extras dev --no-root
export DJANGO_SETTINGS_MODULE=notifications_system.local
python manage.py migrate
python manage.py check
python manage.py test notifications.tests
pytest
```

`local.py` registra la app, usa SQLite, correo en memoria y Celery eager con
broker en memoria. No iniciar workers ni Beat con esta configuración: las
pruebas invocan las tareas directamente. Los canales externos permanecen
inhabilitados; las pruebas de proveedores utilizan mocks. La configuración
SMTP/Redis de `settings.py` es una plantilla y no se usa en estos comandos.

El lockfile se regeneró porque el original no coincidía con pyproject.toml.
Para actualizarlo deliberadamente: `poetry lock`. `.venv`, `.env*`, SQLite,
cachés y `.tmp/` están excluidos de Git. No guardar credenciales en local.py.

## Fiabilidad y límites

Una notificación se identifica por `(uuid, channel_id)`. Celery deriva el UUID
estable del ID de tarea, incluidos los accesos por canal y los lotes. Para
peticiones independientes que deban deduplicarse, proporcionar el mismo UUID
en `NotificationData`; dos tareas con IDs distintos son peticiones distintas.
El UUID no se debe reutilizar entre usuarios o eventos.

Cada intento reclama el registro mediante UPDATE condicional; no mantiene
una transacción abierta durante la llamada al proveedor. Solo PENDING/QUEUED
y FAILED vencido con presupuesto disponible pueden pasar a SENDING. El
contador de reintentos es compartido por las tareas normales y periódicas,
y la espera se mide desde `updated_at`. La tarea principal solicita reintentos
Celery; los accesos por canal y lotes reportan el fallo y usan el reintento
periódico existente. Una notificación programada permanece pendiente hasta
su fecha; `success` indica envío confirmado, no mera aceptación del registro.

No se garantiza entrega exactamente una vez: un timeout puede ocurrir después
de que el proveedor acepte el mensaje. Los proveedores actuales no tienen
una clave de idempotencia de extremo a extremo. Los estados SENDING dejados
por una caída o un fallo de persistencia tras enviar necesitan revisión con
el proveedor; no se recuperan automáticamente. No cambiar manualmente su
estado a FAILED sin comprobar el resultado externo.

La migración 0002 añade unicidad sin borrar datos. En una instalación anterior
con duplicados `(uuid, channel_id)` fallará y exigirá reconciliación manual;
no usar `--fake` ni eliminar registros automáticamente. 0001 es la migración
inicial que faltaba en este clon; las instalaciones con tablas preexistentes
requieren revisar su historial antes de aplicarla.

La concurrencia se prueba con dos conexiones y trabajadores sobre SQLite.
No se ha validado un worker/broker real ni PostgreSQL; no son necesarios para
esta suite. Ruff y Black se usan sobre los archivos modificados; el repositorio
contiene problemas de estilo previos fuera del alcance de esta fase.

```bash
ruff check notifications/__init__.py notifications/models.py notifications/tasks.py \
  notifications/repositories/notification_repository.py \
  notifications/services/notification_service.py notifications/services/email_service.py \
  notifications/tests/ notifications/migrations/ notifications_system/local.py
BLACK_CACHE_DIR=/tmp/notifications-black black --check --workers 1 \
  notifications/__init__.py notifications/models.py notifications/tasks.py \
  notifications/repositories/notification_repository.py \
  notifications/services/notification_service.py notifications/services/email_service.py \
  notifications/tests/ notifications/migrations/ notifications_system/local.py
```

En esta ejecución la CLI de Black verificó los archivos pero no terminó antes
del timeout del entorno. Se comprobó el mismo formato con su API, sin caché:

```bash
python - <<'PY'
from pathlib import Path
import black
paths = [
    "notifications/__init__.py", "notifications/models.py", "notifications/tasks.py",
    "notifications/repositories/notification_repository.py",
    "notifications/services/notification_service.py", "notifications/services/email_service.py",
    "notifications_system/local.py", "notifications_system/celery.py",
    "notifications_system/__init__.py",
]
files = [Path(p) for p in paths]
files += list(Path("notifications/tests").glob("*.py"))
files += list(Path("notifications/migrations").glob("*.py"))
mode = black.Mode(line_length=100, target_versions={black.TargetVersion.PY312})
for path in files:
    source = path.read_text()
    if source.strip():
        try:
            black.format_file_contents(source, fast=False, mode=mode)
        except black.NothingChanged:
            continue
        raise SystemExit(f"Formato pendiente: {path}")
print("Black: formato correcto")
PY
```

## Validación de Fase 1

- 33 pruebas pasan tanto con pytest como con el runner Django (incluyen las 3 originales).
- Cobertura de éxito, excepción/fallo de proveedor, reintento real Celery y
  agotamiento, UUID estable en tareas/canales/lotes, estados terminales,
  trabajadores solapados, programación, preferencias y reenvío de email.
- `manage.py check`: sin incidencias; `makemigrations --check --dry-run`:
  sin cambios; `migrate`: migraciones aplicadas en SQLite local.
- `poetry check --lock`: correcto. Ruff pasa en todos los archivos modificados.
  La revisión global conserva 30 incidencias anteriores en otros archivos.
- Black: verificación por API correcta; limitación de CLI descrita arriba.
- Se comprobó que Git ignora `.venv`, `.env`, `.env.local`, SQLite y cachés.
- No se instalaron servicios del sistema ni se enviaron notificaciones reales.

Además de los defectos de entrega, el clon tenía un `__init__.py` con
codificación incompatible e importaciones anticipadas de modelos, no tenía
migración inicial, y sus pruebas apuntaban a imports/mocks obsoletos. Celery
no cargaba sus settings y utilizaba `os.setenv`, que no existe. Se repararon
estos bloqueos y se verificó despacho eager sin broker externo.
