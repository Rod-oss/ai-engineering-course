# Seguridad en Kestrel

> Documento ficticio creado para el curso de AI Engineering. Kestrel y la empresa Nubaria no existen.

## Gestión de secretos

Las credenciales de Kestrel se guardan únicamente en Bóveda, el gestor de secretos interno de Nubaria. Ningún secreto puede escribirse en el código ni en archivos de configuración del repositorio. Los secretos de producción se rotan cada 90 días. Los servicios obtienen sus credenciales mediante identidades de servicio, nunca con claves personales. El escáner Lupa revisa cada commit y bloquea los que contienen patrones de secretos, como los tokens que empiezan con kst_live_.

## Control de accesos

Se aplica el principio de mínimo privilegio: cada persona recibe solo los permisos que necesita para su trabajo. La autenticación multifactor es obligatoria para todas las herramientas internas. El acceso a producción siempre es temporal: se solicita en el portal Llave, dura como máximo 8 horas, requiere una justificación y debe aprobarlo un líder técnico. Los permisos de todo el equipo se revisan cada trimestre.

## Gestión de vulnerabilidades

Las dependencias de todos los servicios se escanean cada semana. Las vulnerabilidades con puntuación CVSS de 9.0 o más deben corregirse en un máximo de 72 horas. Las de puntuación entre 7.0 y 8.9 tienen un plazo de 14 días. Las de menor gravedad se corrigen en el siguiente ciclo de mantenimiento.

## Protección de datos

Los datos se cifran en reposo con AES-256 y en tránsito con TLS 1.3. Kestrel nunca almacena números de tarjeta: la pasarela de pagos los reemplaza por un token antes de que lleguen a la plataforma. Los datos personales de los clientes se conservan durante 5 años.

## Incidentes de seguridad

Cualquier sospecha de incidente de seguridad se reporta en el canal privado #kestrel-seguridad, nunca en canales abiertos. Si hay exposición de datos de clientes, el incidente se trata como SEV1 y el equipo de protección de datos debe recibir la notificación en un plazo de 24 horas.