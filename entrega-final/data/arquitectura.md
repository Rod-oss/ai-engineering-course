# Kestrel: arquitectura general

> Documento ficticio creado para la Pre-entrega 3 del curso de AI Engineering. Kestrel y la empresa Nubaria no existen.

## Propósito

Kestrel es la plataforma interna de gestión de pedidos de Nubaria. Recibe los pedidos de la tienda en línea, reserva el inventario, calcula el costo de envío y notifica a los clientes. En operación normal atiende en promedio 1.800 pedidos por hora, con picos de hasta 9.000 pedidos por hora durante campañas comerciales.

## Componentes principales

- **Portal**: pasarela de entrada única. Valida los tokens de acceso, aplica los límites de peticiones y enruta cada solicitud al servicio correspondiente. Está escrita en Go y escucha en el puerto 8443.
- **Atlas**: servicio de pedidos. Está escrito en Python 3.12 con FastAPI y es el único servicio que crea y modifica pedidos. Guarda sus datos en la base de datos principal kestrel-db.
- **Brújula**: servicio de inventario, escrito en Go. Gestiona las reservas de stock con bloqueo optimista. Una reserva expira automáticamente a los 12 minutos si el pago no se confirma.
- **Rumbo**: servicio de envíos, escrito en Python. Calcula tarifas con tres paqueterías asociadas y guarda los resultados en caché.
- **Eco**: servicio de notificaciones. Consume eventos de la cola de mensajes y envía correos electrónicos y mensajes SMS a los clientes.

## Datos y almacenamiento

- **Base de datos principal (kestrel-db)**: PostgreSQL 16 en un clúster de tres nodos: un primario y dos réplicas de lectura. Atlas escribe únicamente en el nodo primario. Se hace un respaldo completo todos los días a las 02:00 UTC y los respaldos se conservan 35 días. Además, el registro continuo de transacciones permite recuperar la base a cualquier punto de las últimas 72 horas.
- **Caché**: Redis 7. Rumbo guarda las tarifas de envío durante 15 minutos y Portal guarda los contadores de límite de peticiones.
- **Mensajería**: RabbitMQ. La cola principal se llama pedidos.eventos. Un mensaje que falla cinco veces se mueve a la cola pedidos.muertos para revisión manual.

## Flujo de un pedido

1. La tienda envía el pedido a Portal, que valida el token y lo reenvía a Atlas.
2. Atlas registra el pedido con estado "recibido" y solicita la reserva a Brújula.
3. Brújula reserva el stock y Atlas cambia el estado a "reservado".
4. Cuando la pasarela de pagos confirma el cobro, Atlas cambia el estado a "pagado" y publica un evento en pedidos.eventos.
5. Rumbo asigna la paquetería y Eco envía la confirmación al cliente.
6. Al recibir la guía de la paquetería, el pedido pasa a "enviado".

## Capacidad y objetivos

- Cada instancia de Atlas usa un conjunto de 40 conexiones a la base de datos.
- En operación normal funcionan 6 instancias de Atlas. El autoescalado agrega instancias hasta un máximo de 20 cuando el uso de CPU supera el 70 % durante 5 minutos.
- El objetivo de latencia para crear un pedido es un p95 inferior a 400 ms.
- El objetivo de disponibilidad (SLO) es del 99,9 % mensual.

## Observabilidad

Las métricas se recolectan con Prometheus y se visualizan en el tablero de Grafana "Kestrel / Salud general". Las trazas distribuidas usan OpenTelemetry. Todos los servicios escriben logs en formato JSON e incluyen el campo pedido_id para seguir un pedido de principio a fin.