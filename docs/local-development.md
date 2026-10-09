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
