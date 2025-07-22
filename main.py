from fastapi import FastAPI
import requests

app = FastAPI()

HEADERS = {
    "Content-Type": "application/json"
}

def obtener_promedio(direccion: str):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    data = {
        "page": 1,
        "rows": 10,
        "payTypes": [],
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": direccion.upper()
    }

    response = requests.post(url, headers=HEADERS, json=data)
    anuncios = response.json().get("data", [])

    precios_validos = []

    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        advertiser = anuncio.get("advertiser", {})

        precio = float(adv.get("price", 0))
        min_limit = float(adv.get("minSingleTransAmount", 0))
        condicion_btc = advertiser.get("userType") == "merchant" and "BTC" in adv.get("tradeMethods", [{}])[0].get("tradeMethodName", "")

        if condicion_btc or min_limit > 1000:
            continue

        precios_validos.append(precio)

        if len(precios_validos) == 5:
            break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    return {
        "direccion": direccion,
        "promedio_bs": round(promedio, 2),
        "anuncios_validos": len(precios_validos)
    }

@app.get("/")
def root():
    return {"mensaje": "API de dólar paralelo Bolivia - /compra o /venta"}

@app.get("/compra")
def dolar_compra():
    return obtener_promedio("BUY")

@app.get("/venta")
def dolar_venta():
    return obtener_promedio("SELL")
