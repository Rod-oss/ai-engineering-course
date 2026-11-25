# API pública de Kestrel, versión 2

> Documento ficticio creado para la Pre-entrega 3 del curso de AI Engineering. Kestrel y la empresa Nubaria no existen.

## Autenticación

Todas las peticiones requieren un token en la cabecera Authorization con el esquema Bearer. Los tokens de producción empiezan con kst_live_ y los de pruebas con kst_test_. Cada token es válido durante 180 días y debe rotarse antes de vencer. Un token nunca debe guardarse en el código fuente.

## Límites de uso

Cada token puede hacer hasta 600 peticiones por minuto, con un máximo de 20 peticiones por segundo en ráfagas. Al superar el límite, la API responde con el código 429 e incluye la cabecera Retry-After, que indica cuántos segundos esperar antes de reintentar.

## Endpoints principales

- **POST /v2/pedidos**: crea un pedido. Requiere la cabecera Idempotency-Key, que es válida durante 24 horas y evita crear pedidos duplicados si una petición se reintenta.
- **GET /v2/pedidos/ID**: devuelve un pedido por su identificador.
- **GET /v2/pedidos**: lista pedidos con paginación por cursor. Devuelve 50 resultados por página de forma predeterminada, con un máximo de 200.
- **POST /v2/pedidos/ID/cancelar**: cancela un pedido. Solo es posible mientras el pedido no haya llegado al estado "enviado".

## Estados de un pedido

Un pedido pasa por los estados recibido, reservado, pagado, enviado y entregado. En cualquier momento anterior a "enviado" puede pasar al estado cancelado.

## Códigos de error

- **400**: la petición está mal formada.
- **401**: el token falta, es inválido o venció.
- **409**: la Idempotency-Key ya se usó con un contenido distinto.
- **422**: los datos no superan la validación, por ejemplo un producto sin stock.
- **429**: se superó el límite de peticiones.
- **503**: la plataforma está en mantenimiento programado.

## Webhooks

Kestrel puede avisar a sistemas externos cuando ocurre un evento, como pedido.pagado o pedido.enviado. Cada aviso incluye una firma HMAC-SHA256 en la cabecera X-Kestrel-Firma para verificar su autenticidad. Si el sistema receptor no responde, Kestrel reintenta el envío hasta 8 veces durante 24 horas.

## Versionado

La versión 1 de la API está obsoleta y dejará de funcionar el 31 de marzo de 2027. Las integraciones nuevas deben usar la versión 2.