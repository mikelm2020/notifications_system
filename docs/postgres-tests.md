# Integración con PostgreSQL

Validación Fase 1.2: se inició, con autorización, un contenedor efímero
postgres:16 sin volúmenes y con puerto 55432 publicado solo en loopback.
La suite completa se ejecutó sobre PostgreSQL real con proveedores simulados:
67 pruebas pasaron sin omisiones. SQLite: 62 pasaron y 5 se omitieron por
requerir PostgreSQL. Las tres pruebas originales de rollback pasaron intactas.
El servidor se detuvo al terminar. No se instalaron paquetes del sistema.

```bash
source .venv/bin/activate
poetry install --extras 'dev postgres-tests' --no-root
export DJANGO_SETTINGS_MODULE=notifications_system.postgres_test
export NOTIFICATIONS_PG_USER=notifications_test
export NOTIFICATIONS_PG_PASSWORD=local-test-only
export NOTIFICATIONS_PG_PORT=55432
pytest notifications/tests/test_postgres_integration.py -q
# También ejecutar toda la suite sobre el backend real:
pytest -q
```

La configuración admite solo loopback, usa una conexión de mantenimiento a
`postgres` y Django crea `test_notification_reliability`. Usar un servidor
local dedicado y un usuario de pruebas con CREATEDB, nunca credenciales de
producción. No usar --reuse-db/--keepdb para la validación de migraciones. No
apuntar manage.py migrate a postgres_test: es exclusivamente para los runners
de pruebas. No ejecutar simultáneamente varias suites contra el mismo nombre.

Si Docker está disponible, se puede preparar manualmente un servidor efímero
sin volúmenes, con credenciales ficticias y puerto publicado solo en loopback:

```bash
docker run --rm -d --name notifications-postgres-tests \
  -e POSTGRES_USER=notifications_test -e POSTGRES_PASSWORD=local-test-only \
  -p 127.0.0.1:55432:5432 postgres:16
# Esperar hasta que pg_isready responda antes de ejecutar pytest.
docker exec notifications-postgres-tests pg_isready -U notifications_test
# Al terminar:
docker stop notifications-postgres-tests
```

Los cinco casos específicos PostgreSQL comprueban dos reclamaciones PENDING
simultáneas, dos reclamaciones FAILED con un único incremento, creación
simultánea por UUID/canal, competencia cancelación/inicio del envío y acceso
con select_for_update durante la llamada al proveedor (sin bloqueo de I/O).
SQLite no simula estas garantías: esos cinco casos se omiten explícitamente.
Los nuevos casos de Fase 1.2 verifican commit, pérdida del callback, fallo del
broker, recuperación persistente, reentrega, recuperación frente a worker y
rechazo de publicación de intención sin persistir dentro de atomic.

Los proveedores son fakes/mocks, incluso en PostgreSQL. Celery eager usa
memoria; no se necesita Redis para estas pruebas. Worker/broker reales,
Repeatable Read/Serializable y fallos de red distribuidos siguen sin validarse.
