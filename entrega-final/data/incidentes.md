# Guía de respuesta a incidentes de Kestrel

> Documento ficticio creado para la Pre-entrega 3 del curso de AI Engineering. Kestrel y la empresa Nubaria no existen.

## Niveles de severidad

- **SEV1, crítico**: caída total del servicio o riesgo de pérdida de datos. Ejemplos: Portal no responde, el nodo primario de kestrel-db no acepta escrituras o se detectan cobros duplicados. Tiempo máximo de respuesta: 15 minutos. Se publica una actualización cada 30 minutos y se notifica a la dirección de ingeniería.
- **SEV2, alto**: degradación grave. Ejemplos: más del 5 % de los pedidos termina en error, el p95 de creación de pedidos supera los 2 segundos o la cola pedidos.eventos acumula más de 50.000 mensajes. Tiempo máximo de respuesta: 30 minutos, con actualizaciones cada hora.
- **SEV3, medio**: falla parcial con alternativa disponible. Ejemplos: notificaciones retrasadas o una de las paqueterías no responde. Tiempo máximo de respuesta: 4 horas hábiles.
- **SEV4, bajo**: problemas menores o cosméticos. Se atienden en el siguiente sprint.

## Guardia

La guardia rota cada semana y el cambio de turno es los lunes a las 10:00, hora de la Ciudad de México. Cada turno tiene dos personas: una principal y una secundaria. Si la persona principal no confirma una alerta en 10 minutos, la herramienta de alertas Sirena llama automáticamente a la secundaria.

## Coordinación

Todo incidente SEV1 o SEV2 se coordina en el canal #kestrel-incidentes. Se asignan dos roles: el comandante del incidente, que toma las decisiones y prioriza, y el escriba, que registra la cronología. Para incidentes que afectan a clientes se actualiza además la página de estado pública.

## Runbook: pedidos atascados en "reservado"

1. Revisa el panel "Reservas pendientes" en Grafana.
2. Comprueba que Brújula responde en su verificación de salud.
3. Revisa si hay mensajes acumulados en la cola pedidos.muertos.
4. Reprocesa los mensajes con el comando: kestrel-cli reprocesar --cola pedidos.muertos --max 500
5. Si hay más de 2.000 pedidos atascados, escala el incidente a SEV2.

## Runbook: kestrel-db no acepta escrituras

Este caso es siempre SEV1. Para promover una réplica a primario se usa el comando kestrel-cli db promover --replica kestrel-db-2. La promoción requiere la aprobación de las dos personas de guardia y solo debe hacerse si el retraso de replicación es menor a 5 segundos.

## Postmortem

Todo incidente SEV1 o SEV2 requiere un postmortem en un plazo de 5 días hábiles. El formato es sin culpables: se analizan causas y procesos, no personas. Cada acción correctiva debe tener una persona responsable y una fecha de entrega.