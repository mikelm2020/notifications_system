# Instalaciones con tablas existentes

0001 y 0002 se conservan sin modificaciones. 0003 agrega dos timestamps
nullable: comienzo del despacho y fallo permanente. No borra registros ni
reconcilia UUID duplicados. La suite aislada verifica el recorrido inicial,
unicidad y campos nuevos, preservando el contenido del registro existente.
Eso no certifica el esquema de ninguna instalación externa.

Antes de actualizar una instalación, inventariar su historial real:

```sql
SELECT app, name, applied
FROM django_migrations
WHERE app = 'notifications'
ORDER BY name;

SELECT uuid, channel_id_id, COUNT(*) AS cantidad
FROM notifications_notification
GROUP BY uuid, channel_id_id
HAVING COUNT(*) > 1;
```

Comparar todas las tablas, columnas, tipos, nullabilidad, foreign keys,
índices y restricciones contra 0001, además del modelo de usuario real.
Django no comprueba checksums de las migraciones ya registradas: un 0001
creado por otro proyecto puede tener el mismo nombre y contenido diferente.
En esquemas parcialmente creados, migrate normal puede fallar al encontrar
la primera tabla existente. Tener los mismos nombres de tablas no basta.

`--fake-initial` detecta presencia de tablas/columnas de las operaciones
CreateModel/AddField, pero no verifica el esquema completo ni crea índices
omitidos al simular la migración. No ejecutarlo sin validar primero el esquema
y acordar un procedimiento de adopción. No usar --fake para eludir 0002, no
editar django_migrations y no borrar registros para forzar la actualización.
Durante esta fase no se aplicaron migraciones artificialmente en bases reales.

Un UUID repetido en distintos canales es compatible con 0002. Un UUID/canal
repetido no lo es, incluso con distintos usuarios, eventos o estados. Revisar
si esos UUID representaban correlación o identidad de entrega: no asumir que
las filas duplicadas son descartables. Resolverlo requiere una decisión sobre
los datos de esa instalación; esta rama no hace deduplicación automática.

En PostgreSQL añadir la unicidad puede requerir un bloqueo de tabla. Evaluar
el volumen, tráfico y ventana de mantenimiento; la rama no implementa creación
de índices concurrente para despliegues sin parada. También revisar los FAILED
históricos con errores de transporte y los SENDING antes de habilitar tareas
periódicas: los resultados externos pueden ser inciertos.
