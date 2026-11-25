# Datos, respaldos y recuperación de Kestrel

> Documento ficticio creado para el curso de AI Engineering. Kestrel y la empresa Nubaria no existen.

## Objetivos de recuperación

Para la base de datos principal kestrel-db se definieron dos objetivos. El RPO, la cantidad máxima de datos que se acepta perder, es de 15 minutos. El RTO, el tiempo máximo para volver a operar después de un desastre, es de 1 hora.

## Política de respaldos

Se hace un respaldo completo todos los días a las 02:00 UTC y respaldos incrementales cada 6 horas. Todos los respaldos se cifran y se copian a un segundo centro de datos. Se conservan durante 35 días. El registro continuo de transacciones permite recuperar la base a cualquier minuto de las últimas 72 horas.

## Restauración de la base de datos

La restauración se hace con el comando kestrel-cli db restaurar --punto seguido de la fecha y hora deseadas, por ejemplo "2026-11-20 14:30". El comando nunca sobrescribe la base original: crea una base nueva llamada kestrel-db-restaurada. Después hay que validar la integridad con kestrel-cli db verificar. Mover el tráfico a la base restaurada requiere la aprobación del comandante del incidente.

## Simulacros de recuperación

Cada trimestre se realiza el simulacro Ancla: el equipo restaura la base en un entorno aislado y mide el tiempo real de recuperación contra el RTO. En el último simulacro, la recuperación completa tardó 41 minutos. Los hallazgos se registran como acciones de mejora con responsable y fecha.

## Retención y borrado

Los eventos de la cola de mensajes se conservan 7 días y los logs de los servicios, 30 días. Las solicitudes de borrado de datos personales de un cliente se atienden en un máximo de 15 días hábiles.