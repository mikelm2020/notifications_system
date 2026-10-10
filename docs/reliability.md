# Fiabilidad: Fase 1.1

> Nota de versión: este documento conserva resultados históricos de las Fases 1 y 1.1.
> La decisión transaccional y los fallos de rollback aquí descritos se resolvieron
> en Fase 1.2; PostgreSQL y CI se validaron después. Para el comportamiento actual,
> consultar [despacho transaccional](transactional-dispatch.md),
> [pruebas PostgreSQL](postgres-tests.md) y [CI](ci.md).

## Transiciones soportadas

Las operaciones del repositorio hacen UPDATE condicionado por estado. No
hay un bloqueo de fila que deba conservarse durante HTTP/SMTP en autocommit.
Las escrituras directas por ORM, SQL o receptores propios pueden saltarse
estas reglas y no forman parte del contrato de cancelación segura.

| Origen | Destino | Condición |
| --- | --- | --- |
| PENDING / QUEUED | SENDING | Fecha vencida; reclamación ganada; sin fallo permanente |
| FAILED | SENDING | Presupuesto disponible, espera vencida y resultado no ambiguo |
| PENDING / QUEUED / FAILED | CANCELLED | Sin fallo permanente; cancelación explícita o preferencias deshabilitadas |
| SENDING | CANCELLED | `dispatch_started_at` todavía es NULL |
| SENDING | FAILED | Preparación fallida o respuesta negativa de envío |
| SENDING | SENT / READ | Envío confirmado del intento propietario; READ si `is_read` ya estaba activo |
| SENT / DELIVERED | READ | Lectura del usuario |
| SENDING | SENDING | Resultado ambiguo: retención para revisión, sin replay automático |

`begin_dispatch()` y `cancel()` compiten mediante UPDATE condicional. La
cancelación gana hasta que se registra el comienzo de la llamada. Después
no puede revocar una llamada externa ni impedir una aceptación remota. El
último chequeo de preferencias se hace después de `notification_pre_send`.
Los estados SENT, DELIVERED, READ, CANCELLED y SENDING no pueden reclamarse
otra vez. La lectura de un registro fallido no cambia su estado de entrega.
No se añadió un callback nuevo de confirmación DELIVERED.

Los resultados se guardan solo si el estado y `dispatch_started_at` coinciden
con el intento propietario. Una finalización tardía no debe sobrescribir
otro estado. Marcar SENT exige haber iniciado el envío; ya no se puede pasar
PENDING directamente a SENT con el repositorio.

## Presupuestos y fallo permanente

`max_retries` permite un intento inicial y hasta ese número de reintentos.
`retry_count` comienza en cero y aumenta únicamente al reclamar FAILED. La
reclamación condicional comparte el presupuesto entre Celery y Beat. Los
fallos de infraestructura anteriores a la reclamación no inventan intentos.

Celery mantiene además un límite de reprogramaciones del mensaje. Al agotar
cualquiera de los dos presupuestos, los registros FAILED conocidos se marcan
con `failed_permanently_at` antes de avisar. Esta marca impide reclamaciones
posteriores incluso si cambia la configuración o se repite el mensaje. No
se aumenta artificialmente `retry_count` para representar un agotamiento de
Celery. No se emite una señal de fallo de entrega sin un registro persistido.

La señal permanente se reserva con un UPDATE y se despacha con `send_robust`.
Un receptor fallido no puede habilitar otro envío. Esto no es un outbox de
eventos: una caída entre la reserva y el despacho puede perder el aviso. No
se garantiza entrega exactamente una vez de signals.

## Preferencias e incertidumbre

Un reintento con UUID existente recupera el conjunto original de registros;
no lo sustituye por una lista vacía si cambiaron las preferencias. La
preferencia deshabilitada cancela la entrega que aún puede cancelarse. La
tarea devuelve éxito solamente si hay registros y todos están confirmados.
Una cancelación o un conjunto vacío no es una confirmación de envío.

Timeouts y desconexiones de transporte reconocidos producen
`error_code=DELIVERY_UNKNOWN`, conservando SENDING. Una pérdida de persistencia
después de aceptar el envío también mantiene SENDING. No se reintentan esos
registros. Los códigos ambiguos anteriores (por ejemplo TIMEOUT) también
se excluyen de las reclamaciones FAILED, sin modificar los registros antiguos.

Los adaptadores personalizados deben distinguir rechazos conocidos de
resultados ambiguos. El contrato booleano existente conserva False para un
rechazo; no permite inferir todos los fallos desconocidos de cualquier SDK.
Un timeout puede ocurrir después de aceptación; una revisión con el proveedor
es necesaria. No hay garantía de entrega exactamente una vez ni soporte de
idempotencia universal. La entrega por dispositivo de los canales multicast
no se convirtió en registros separados en esta fase.

## Transacción exterior: decisión pendiente

La corrección de rollback necesita decidir el comportamiento público de una
llamada síncrona dentro de `transaction.atomic()`. La propuesta sometida a
aprobación es conservar QUEUED en la transacción, usar `on_commit()` para el
primer intento y recuperar la cola mediante una tarea periódica persistente.
El método devolvería un registro pendiente dentro de la transacción, y
seguiría enviando inmediatamente en autocommit.

`on_commit()` solo elimina envíos de transacciones revertidas. No garantiza
entrega ante caída del proceso después de commit; la cola persistente y su
recuperación son necesarias. La alternativa es rechazar explícitamente
llamadas de envío dentro de transacciones. Hasta resolver esta decisión las
pruebas de rollback reproducen el defecto y la rama no está lista para publicar.
