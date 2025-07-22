from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from datetime import datetime

app = FastAPI()

def obtener_promedio(trade_type):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": trade_type,
        "page": 1,
        "rows": 10,
        "payTypes": [],
        "publisherType": None
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    precios = [float(oferta["adv"]["price"]) for oferta in data["data"]]
    promedio = sum(precios) / len(precios)
    return round(promedio, 2)

@app.get("/dolar-paralelo")
def dolar_paralelo():
    try:
        promedio_venta = obtener_promedio("SELL")  # Gente que vende USDT
        promedio_compra = obtener_promedio("BUY")  # Gente que compra USDT
        ahora = datetime.now().isoformat()

        return JSONResponse({
            "fuente": "Binance P2P",
            "moneda": "USDT",
            "fiat": "BOB",
            "promedio_venta": promedio_venta,
            "promedio_compra": promedio_compra,
            "hora_actualizacion": ahora
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
