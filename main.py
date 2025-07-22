from fastapi import FastAPI
import requests

app = FastAPI()

def obtener_promedio(tipo: str) -> float:
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": tipo.upper(),
        "page": 1,
        "rows": 10,
        "payTypes": [],
        "publisherType": None
    }
    res = requests.post(url, headers=headers, json=payload)
    data = res.json()
    precios = [float(ad["adv"]["price"]) for ad in data["data"]]
    return sum(precios) / len(precios)

@app.get("/")
def raiz():
    return {"mensaje": "API Dólar Paralelo Bolivia 🟦"}

@app.get("/dolar-paralelo")
def dolar_paralelo():
    compra = obtener_promedio("BUY")
    venta = obtener_promedio("SELL")
    promedio = round((compra + venta) / 2, 2)
    return {
        "compra": round(compra, 2),
        "venta": round(venta, 2),
        "promedio": promedio,
        "fuente": "Binance P2P"
    }
