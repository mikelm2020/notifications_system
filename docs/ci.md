# Integración continua

`.github/workflows/ci.yml` se ejecuta en cada Pull Request y en cada push a
`main`. Usa Ubuntu 24.04, Python 3.12, Poetry 2.4.1 y PostgreSQL 16 como servicio
con health check. Solo concede `contents: read`, no conserva credenciales de
checkout y cancela ejecuciones anteriores del mismo PR/rama. El job tiene un
límite de 15 minutos y la suite de 5 minutos.

Instala desde `poetry.lock`, sin instalar el proyecto como paquete, y ejecuta:

```bash
poetry check --lock
poetry install --extras 'dev postgres-tests' --no-root
xargs -d '\n' -r poetry run ruff check -- < .github/ruff-files.txt
poetry run python manage.py check
poetry run python manage.py makemigrations --check --dry-run
poetry run pytest -q --junitxml=test-results.xml
```

Ruff usa `.github/ruff-files.txt`: todos los archivos Python modificados por el
PR de fiabilidad al introducir CI, incluidas migraciones, estrategias y pruebas.
Es una lista estable para que el mismo alcance se siga verificando al integrar
el PR en main. Ampliarla al añadir archivos al área de fiabilidad. No se usa
`--fix`, no se ignoran reglas adicionales y no se hace limpieza histórica del
resto del repositorio.

`DJANGO_SETTINGS_MODULE=notifications_system.postgres_test` selecciona una base
real aislada y evita que las pruebas PostgreSQL se omitan. Django crea y elimina
`test_notification_reliability`; no se reutiliza. Las credenciales literales son
exclusivamente de este servicio efímero y no utilizan GitHub Secrets. El usuario
del contenedor puede crear la base de pruebas. Email usa locmem, Celery usa eager
y memoria, y los proveedores externos se simulan en las pruebas. No hacen falta
Redis ni credenciales de Twilio, Slack, Firebase u otros proveedores.

Para reproducirlo, usar Python 3.12 y Poetry 2.4.1, iniciar el contenedor aislado
según [postgres-tests.md](postgres-tests.md), esperar a `pg_isready` y ejecutar
los comandos anteriores desde la raíz con estas variables:

```bash
export DJANGO_SETTINGS_MODULE=notifications_system.postgres_test
export NOTIFICATIONS_PG_HOST=127.0.0.1
export NOTIFICATIONS_PG_PORT=55432
export NOTIFICATIONS_PG_USER=notifications_test
export NOTIFICATIONS_PG_PASSWORD=local-test-only
export POETRY_VIRTUALENVS_IN_PROJECT=true
export POETRY_NO_INTERACTION=1
```

Al terminar, detener el contenedor como indica esa guía. No ejecutar `migrate`
contra la conexión de mantenimiento `postgres`. Una validación local no equivale
a una ejecución de GitHub Actions: consultar el check CI del PR o la pestaña
Actions para conocer el resultado remoto.

La configuración del servicio sigue el [patrón documentado por GitHub](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).
