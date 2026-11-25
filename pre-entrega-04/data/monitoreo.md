# Monitoreo y alertas de Kestrel

> Documento ficticio creado para el curso de AI Engineering. Kestrel y la empresa Nubaria no existen.

## Señales que se vigilan

El monitoreo de Kestrel se basa en cuatro señales: latencia, tráfico, errores y saturación de recursos. Cada servicio expone sus métricas a Prometheus.

## Alertas principales

- AtlasLatenciaAlta: el p95 de creación de pedidos supera 1 segundo durante 10 minutos. Avisa a la guardia y suele ser el primer síntoma de un incidente SEV2.
- AtlasErroresElevados: más del 2 % de las peticiones a Atlas termina en error durante 5 minutos.
- ColaEventosAcumulada: la cola pedidos.eventos supera los 20.000 mensajes pendientes.
- BrujulaReservasVencidas: vencen más de 100 reservas de inventario en 15 minutos.
- KestrelDBReplicacionLenta: el retraso de las réplicas de kestrel-db supera los 30 segundos.

## Enrutamiento de alertas

Las alertas se envían mediante Sirena. Las alertas críticas llaman por teléfono a la persona de guardia a cualquier hora. Las advertencias se publican en el canal #kestrel-alertas y se revisan en horario laboral.

## Presupuesto de error

Con un objetivo de disponibilidad del 99,9 %, Kestrel puede estar fuera de servicio unos 43 minutos al mes. Ese margen se llama presupuesto de error. Si el presupuesto se consume al doble de la velocidad normal durante una hora, se congelan los despliegues que no sean urgentes.

## Tableros

Los tableros principales en Grafana son "Kestrel / Salud general", "Kestrel / Pedidos" y "Kestrel / Base de datos".

## Cómo crear una alerta nueva

Toda alerta nueva debe ser accionable, tener un runbook enlazado y revisarse 30 días después de crearse. Una alerta que se dispara sin requerir ninguna acción debe ajustarse o eliminarse.