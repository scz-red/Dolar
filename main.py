from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime

app = FastAPI()

# Configuración CORS para permitir peticiones desde frontend
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:5500",
    "https://tu-dominio.com",  # Cambia aquí por tu dominio real
    "*",  # Para desarrollo, permite todos los orígenes (ajustar en producción)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CRYPTO_MAP = {
    "USDT": "tether",
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDC": "usd-coin",
    "DOGE": "dogecoin",
    "SOL": "solana",
    "PEPE": "pepe",
    "TRUMP": "trumpcoin"
}

def obtener_promedio(direccion: str):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    data = {
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": direccion,
        "page": 1,
        "rows": 10,
        "payTypes": [],
        "publisherType": None
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        anuncios = response.json().get("data", [])
    except Exception as e:
        return {"error": f"Error al consultar Binance: {str(e)}"}

    precios_validos = []
    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        min_trans = adv.get("minSingleTransAmount", 0)
        if min_trans and float(min_trans) > 2000:
            continue
        precio = float(adv.get("price", 0))
        precios_validos.append(precio)
        if len(precios_validos) >= 5:
            break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    return {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios_validos)}

def obtener_tasa(base: str, destino: str):
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data['rates'].get(destino)
    except Exception as e:
        print(f"Error API open.er-api.com: {e}")
        return None

@app.get("/convertir_bob")
def convertir_bob(monto_bob: float = Query(1000, description="Monto en bolivianos a convertir")):
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}

    tc_bob_usd = resultado_promedio.get("promedio_bs")
    if not tc_bob_usd:
        return {"error": "No se pudo obtener tipo de cambio paralelo."}

    usd = monto_bob / tc_bob_usd

    monedas = {
        "USD": "Dólar estadounidense",
        "COP": "Peso colombiano",
        "ARS": "Peso argentino",
        "CLP": "Peso chileno",
        "BRL": "Real brasileño",
        "PEN": "Sol peruano",
        "EUR": "Euro",
        "CNY": "Yuan chino",
        "PYG": "Guaraní paraguayo",
        "MXN": "Peso mexicano"
    }

    conversiones_fiat = {}
    for codigo, nombre in monedas.items():
        tasa = obtener_tasa("USD", codigo)
        if tasa:
            valor = usd * tasa
            conversiones_fiat[nombre] = round(valor, 2)
        else:
            conversiones_fiat[nombre] = "No disponible"

    cripto_ids = ",".join(CRYPTO_MAP.values())
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cripto_ids}&vs_currencies=usd"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        precios_criptos = r.json()
    except Exception as e:
        precios_criptos = {}

    conversiones_cripto = {}
    for cripto, cripto_id in CRYPTO_MAP.items():
        if cripto == "USDT":
            conversiones_cripto["Tether (USDT)"] = round(usd, 2)
        else:
            precio = precios_criptos.get(cripto_id, {}).get("usd")
            if precio:
                valor = usd / precio
                conversiones_cripto[cripto] = round(valor, 6)
            else:
                conversiones_cripto[cripto] = "No disponible"

    return {
        "monto_bob": monto_bob,
        "tc_bob_usd": tc_bob_usd,
        "monto_usd": round(usd, 2),
        "conversiones_fiat": conversiones_fiat,
        "conversiones_cripto": conversiones_cripto,
        "timestamp": datetime.now().isoformat()
    }
