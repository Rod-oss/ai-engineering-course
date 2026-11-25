# Política de despliegues de Kestrel

> Documento ficticio creado para la Pre-entrega 3 del curso de AI Engineering. Kestrel y la empresa Nubaria no existen.

## Ventanas de despliegue

Los despliegues a producción se hacen los martes y jueves, entre las 11:00 y las 15:00, hora de la Ciudad de México. No se despliega los viernes ni en vísperas de días festivos. Existe un congelamiento anual de cambios del 15 de diciembre al 6 de enero, y también durante las 48 horas previas a campañas comerciales como la Semana Naranja.

## Requisitos previos

- El cambio debe tener dos aprobaciones en la solicitud de cambios, y al menos una debe venir del equipo dueño del servicio.
- Todas las pruebas automáticas deben pasar. En Atlas se exige una cobertura mínima de pruebas del 80 %.
- Las migraciones de base de datos deben ser compatibles con la versión anterior del código, siguiendo el patrón de expandir y luego contraer.
- El registro de cambios del servicio debe estar actualizado.

## Despliegue canario

Toda versión nueva empieza como canario: recibe el 5 % del tráfico durante 30 minutos. En esa fase se vigilan la tasa de errores, el p95 de latencia y el consumo de memoria. Si todo está bien, se promueve al 25 % del tráfico durante 20 minutos y, después, al 100 %.

## Criterios de reversión

La versión se revierte de inmediato si ocurre cualquiera de estas situaciones:

- La tasa de errores supera el 2 % durante 5 minutos consecutivos.
- El p95 de latencia supera los 800 ms.
- Se dispara una alerta de severidad SEV1 o SEV2.

La reversión se hace con el comando kestrel-cli desplegar revertir --servicio nombre-del-servicio y tarda menos de 3 minutos. Después de revertir hay que avisar en el canal #kestrel-despliegues y, si hubo clientes afectados, abrir un incidente.

## Interruptores de funcionalidad

Las funciones nuevas se publican apagadas, detrás de un interruptor de la herramienta Interruptor, y se encienden de forma gradual. Un interruptor temporal no puede durar más de 90 días: pasado ese plazo hay que eliminarlo del código.

## Despliegues de emergencia

Fuera de las ventanas solo se permiten despliegues para corregir incidentes SEV1 o SEV2. Requieren la aprobación del comandante del incidente y de un líder técnico, y siguen igualmente la fase canaria, aunque reducida a 10 minutos.