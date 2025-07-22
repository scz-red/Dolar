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
        "rows": 20,  # Aumentamos para tener más opciones y evitar filtros estrictos
        "payTypes": [],
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": direccion.upper()
    }

    try:
        response = requests.post(url, headers=HEADERS, json=data)
        response.raise_for_status()
    except Exception as e:
        return {"error": "Error al conectar con Binance", "detalle": str(e)}

    anuncios = response.json().get("data", [])
    precios_validos = []

    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        advertiser = anuncio.get("advertiser", {})

        try:
            precio = float(adv.get("price", 0))
            min_limit = float(adv.get("minSingleTransAmount", 0))
        except (ValueError, TypeError):
            continue

        # 🛡️ Filtro: solo límites razonables
        if not (10 <= min_limit <= 10000):
            continue

        # ✅ Pasó los filtros
        precios_validos.append(precio)

        # Tomamos solo los primeros 5 válidos
        if len(precios_validos) == 5:
            break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

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
