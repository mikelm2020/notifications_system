# Fase 1.2: intención persistente y despacho tras commit

Los servicios públicos síncronos (incluidos API, email y reenvío), las tareas
Celery de creación, batch y canales, las tareas programadas y los reintentos
convergen en NotificationService. La creación de todos los canales se realiza
en un bloque atomic; cada fila nace QUEUED, con contexto y fecha programada.
Esa fila es la intención persistente, sin una segunda cola de base de datos.

Sin transacción exterior, on_commit despacha sincrónicamente para conservar
los resultados actuales. Dentro de atomic, devuelve QUEUED y on_commit publica
dispatch_notification por clave primaria. El callback captura fallos del broker:
la intención confirmada permanece recuperable. Rollback exterior o de savepoint
descarta filas, cambios de estado y callbacks. _send_notification también difiere
las llamadas directas realizadas dentro de atomic. Las transacciones manuales
con autocommit desactivado fuera de atomic no están soportadas.

Celery Beat ejecuta recover_queued_notifications cada minuto. Requiere Beat y
workers activos; también puede invocarse manualmente la tarea de recuperación.
Escanea QUEUED confirmadas y vencidas y despacha por el mismo método y UPDATE
condicional que dispatch_notification. La reentrega no añade un envío. No se
mantienen bloques atomic ni bloqueos de filas durante I/O del proveedor.
process_scheduled_notifications admite PENDING heredadas y QUEUED.
retry_failed_notifications conserva el presupuesto, el retardo y las exclusiones
de resultados ambiguos. Cancelación, estados terminales y failed_permanently_at
siguen protegidos por las condiciones atómicas de Fase 1.1.

## Compatibilidad

- Dentro de una transacción, los consumidores reciben QUEUED; deben volver a
  consultar el estado después del commit. Los objetos devueltos no se actualizan
  automáticamente por un worker. Fuera de atomic el envío sigue siendo síncrono.
- Las notificaciones programadas nuevas nacen QUEUED, en vez de PENDING.
- AsyncNotificationService se puede importar ahora desde services.async_service.
  Persiste antes de publicar y devuelve UUID de entrega, no ID de tarea Celery.
  La programación se guarda en scheduled_for y no depende de un countdown del
  broker. Se corrigieron el nombre de tarea inexistente y el uso de timezone.
- Las tareas Celery de creación siguen aceptando sus argumentos actuales. Un
  .delay() directo es una primitiva de broker: no crea intención en la transacción
  del productor. Las tareas de creación rechazan apply_async/delay dentro de
  transacciones abiertas, incluido eager, antes de publicar. Para producir
  notificaciones vinculadas a negocio, usar el
  servicio síncrono dentro de atomic o AsyncNotificationService; reservar esas
  tareas de creación para invocaciones independientes ya confirmadas. No usar
  sus .delay() para implementar atomicidad con cambios de negocio.

## Límites

Un fallo después de reclamar SENDING no vuelve automáticamente a QUEUED.
SENDING y DELIVERY_UNKNOWN requieren revisión: reciclarlos podría duplicar un
resultado aceptado por el proveedor. Se recupera automáticamente la ventana
posterior al commit y anterior a la reclamación. No hay garantía exactamente una
vez frente al proveedor ni validación de un broker/worker real en estas pruebas.
El escaneo recorre la cola completa; para volúmenes grandes conviene medir y
limitar lotes o agregar un índice según la carga.
