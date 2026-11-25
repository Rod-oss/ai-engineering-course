"""Herramientas del agente: simulan consultas a la base de datos de la tienda."""
import asyncio
import difflib
import json
import unicodedata

from langchain_core.tools import tool

CLIENTES: dict[int, dict] = {
    101: {"nombre": "Ana Torres", "ciudad": "Guadalajara"},
    102: {"nombre": "Mariana López", "ciudad": "Monterrey"},
    103: {"nombre": "Ana Ruiz", "ciudad": "Puebla"},
    104: {"nombre": "Diego Herrera", "ciudad": "Querétaro"},
}

PEDIDOS: list[dict] = [
    {"pedido_id": "P-1001", "cliente_id": 102, "fecha": "2026-09-14", "total": 4200,
     "estado": "entregado", "productos": ["Audífonos inalámbricos"]},
    {"pedido_id": "P-1003", "cliente_id": 101, "fecha": "2026-09-20", "total": 1500,
     "estado": "entregado", "productos": ["Funda para laptop"]},
    {"pedido_id": "P-1007", "cliente_id": 102, "fecha": "2026-10-02", "total": 6800,
     "estado": "entregado", "productos": ["Monitor de 27 pulgadas"]},
    {"pedido_id": "P-1009", "cliente_id": 103, "fecha": "2026-10-11", "total": 12000,
     "estado": "pagado", "productos": ["Silla ergonómica", "Escritorio ajustable"]},
    {"pedido_id": "P-1012", "cliente_id": 101, "fecha": "2026-10-28", "total": 2900,
     "estado": "cancelado", "productos": ["Cámara web"]},
    {"pedido_id": "P-1015", "cliente_id": 102, "fecha": "2026-11-18", "total": 3500,
     "estado": "enviado", "productos": ["Teclado mecánico", "Mouse ergonómico"]},
]


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.lower().split())

def _coincide(buscado: str, nombre: str) -> bool:
    """Cada palabra buscada debe ser el inicio de alguna palabra del nombre."""
    palabras = _normalizar(nombre).split()
    return all(any(palabra.startswith(t) for palabra in palabras) for t in buscado.split())

def _json(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False)


@tool
async def buscar_cliente(nombre: str) -> str:
    """Busca clientes de la tienda por su nombre completo o por una parte del nombre.

    Úsala SIEMPRE que el usuario mencione a un cliente por su nombre, antes de consultar
    pedidos, porque las demás herramientas necesitan el cliente_id numérico.

    Devuelve uno de estos resultados:
    - Una sola coincidencia: el cliente_id, el nombre y la ciudad.
    - Varias coincidencias: la lista de clientes. En ese caso NO elijas uno: pide al
      usuario que aclare a cuál se refiere.
    - Ninguna coincidencia: sugerencias de nombres parecidos. Si alguna sugerencia
      coincide claramente con lo que pidió el usuario, vuelve a llamar a esta
      herramienta con el nombre sugerido.
    """
    await asyncio.sleep(0.2)  # simula la latencia de una consulta a la base de datos
    buscado = _normalizar(nombre)
    coincidencias = [
        {"cliente_id": cid, **datos}
        for cid, datos in CLIENTES.items()
        if _coincide(buscado, datos["nombre"])
    ]
    if len(coincidencias) == 1:
        return _json({"resultado": "encontrado", "cliente": coincidencias[0]})
    if coincidencias:
        return _json({"resultado": "ambiguo", "coincidencias": coincidencias,
                      "nota": "Hay varios clientes con ese nombre. Pide una aclaración al usuario."})
    nombres = {_normalizar(d["nombre"]): d["nombre"] for d in CLIENTES.values()}
    parecidos = difflib.get_close_matches(buscado, list(nombres), n=3, cutoff=0.6)
    return _json({"resultado": "sin_coincidencias", "nombre_buscado": nombre,
                  "sugerencias": [nombres[p] for p in parecidos]})


@tool
async def buscar_pedidos(cliente_id: int) -> str:
    """Consulta el resumen de pedidos de un cliente a partir de su cliente_id numérico.
    Usa ÚNICAMENTE nombres que el usuario haya escrito en la conversación. Nunca inventes
    ni supongas un nombre para buscarlo.
    Devuelve la cantidad de pedidos, el total gastado en pesos mexicanos (MXN) y la lista
    de pedidos con pedido_id, fecha, total y estado, ordenados del más antiguo al más
    reciente. El último elemento de la lista es el pedido más reciente.

    Requiere el cliente_id: si solo conoces el nombre, usa antes buscar_cliente.
    Si el cliente_id no existe, la herramienta devuelve un error.
    """
    await asyncio.sleep(0.2)
    if cliente_id not in CLIENTES:
        raise ValueError(
            f"No existe ningún cliente con cliente_id={cliente_id}. "
            "Usa buscar_cliente para obtener un id válido."
        )
    pedidos = sorted((p for p in PEDIDOS if p["cliente_id"] == cliente_id), key=lambda p: p["fecha"])
    resumen = [{k: p[k] for k in ("pedido_id", "fecha", "total", "estado")} for p in pedidos]
    return _json({
        "cliente_id": cliente_id,
        "nombre": CLIENTES[cliente_id]["nombre"],
        "cantidad_pedidos": len(pedidos),
        "total_mxn": sum(p["total"] for p in pedidos),
        "pedidos": resumen,
    })


@tool
async def obtener_detalle_pedido(pedido_id: str) -> str:
    """Devuelve el detalle completo de un pedido: productos, fecha, total en MXN, estado y
    ciudad de envío.

    Requiere el pedido_id con formato P-NNNN (por ejemplo, P-1015), que aparece en el
    resultado de buscar_pedidos. Si el pedido no existe, devuelve un error.
    """
    await asyncio.sleep(0.2)
    pedido = next((p for p in PEDIDOS if p["pedido_id"] == pedido_id.strip().upper()), None)
    if pedido is None:
        return _json({"error": f"No existe el pedido {pedido_id}. Verifica el id con buscar_pedidos."})
    return _json({**pedido, "ciudad_envio": CLIENTES[pedido["cliente_id"]]["ciudad"]})


HERRAMIENTAS = [buscar_cliente, buscar_pedidos, obtener_detalle_pedido]