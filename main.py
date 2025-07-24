from fastapi import FastAPI
import requests
from datetime import datetime

app = FastAPI()

HEADERS = {
    "Content-Type": "application/json"
}

def obtener_promedio(direccion: str):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    data = {
        "page": 1,
        "rows": 20,
        "payTypes": [],
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": direccion.upper()
    }
    try:
        response = requests.post(url, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status()
        anuncios = response.json().get("data", [])
    except Exception as e:
        return {
            "error": "Error al consultar Binance",
            "detalle": str(e),
            "timestamp": datetime.now().isoformat()
        }

    precios_validos = []

    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        # advertiser = anuncio.get("advertiser", {})  # No se usa
        precio = float(adv.get("price", 0))
        # min_limit = float(adv.get("minSingleTransAmount", 0))  # No se usa
        conditions = adv.get("tradeMethods", [])

        # Filtro PRO: solo toma anuncios SIN restricciones "BTC" en tradeMethodName o identifier
        restricciones = any(
            (
                (method.get("tradeMethodName") and "BTC" in method.get("tradeMethodName").upper())
                or
                (method.get("identifier") and "BTC" in method.get("identifier").upper())
            )
            for method in conditions
        )

        if restricciones:
            continue

        precios_validos.append(precio)

        if len(precios_validos) == 5:
            break

    if not precios_validos:
        return {
            "error": "No hay suficientes anuncios válidos.",
            "direccion": direccion.lower(),
            "timestamp": datetime.now().isoformat()
        }

    promedio = sum(precios_validos) / len(precios_validos)
    return {
        "direccion": direccion.lower(),
        "promedio_bs": round(promedio, 2),
        "anuncios_validos": len(precios_validos),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/")
def root():
    return {"mensaje": "API de dólar paralelo Bolivia - /compra | /venta | /dolar-paralelo"}

@app.get("/compra")
def dolar_compra():
    return obtener_promedio("BUY")

@app.get("/venta")
def dolar_venta():
    return obtener_promedio("SELL")

@app.get("/dolar-paralelo")
def dolar_paralelo():
    compra = obtener_promedio("BUY")
    venta = obtener_promedio("SELL")
    return {
        "fuente": "Binance P2P",
        "timestamp": datetime.now().isoformat(),
        "compra_bs": compra.get("promedio_bs"),
        "venta_bs": venta.get("promedio_bs"),
        "anuncios_compra": compra.get("anuncios_validos"),
        "anuncios_venta": venta.get("anuncios_validos")
    }
