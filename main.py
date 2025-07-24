from fastapi import FastAPI, Query
import requests
from datetime import datetime, timedelta

app = FastAPI()

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

CACHE = {
    "promedio": {"value": None, "timestamp": datetime.min},
    "tasas": {"value": {}, "timestamp": datetime.min},
    "criptos": {"value": {}, "timestamp": datetime.min}
}

CACHE_TTL = timedelta(seconds=60)  # Tiempo de caché, ajustar según necesidad

def obtener_promedio(direccion: str):
    ahora = datetime.now()
    if CACHE["promedio"]["value"] and ahora - CACHE["promedio"]["timestamp"] < CACHE_TTL:
        return CACHE["promedio"]["value"]

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
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=10)
        response.raise_for_status()
        anuncios = response.json().get("data", [])
    except Exception as e:
        return {
            "error": "Error al consultar Binance",
            "detalle": str(e),
            "timestamp": ahora.isoformat()
        }

    precios_validos = []
    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        restricciones = adv.get("minSingleTransAmount", 0)
        if restricciones and float(restricciones) > 2000:
            continue
        precio = float(adv.get("price", 0))
        precios_validos.append(precio)
        if len(precios_validos) == 5:
            break

    if not precios_validos:
        resultado = {
            "error": "No hay suficientes anuncios válidos.",
            "direccion": direccion.lower(),
            "timestamp": ahora.isoformat()
        }
    else:
        promedio = sum(precios_validos) / len(precios_validos)
        resultado = {
            "direccion": direccion.lower(),
            "promedio_bs": round(promedio, 2),
            "anuncios_validos": len(precios_validos),
            "timestamp": ahora.isoformat()
        }

    CACHE["promedio"] = {"value": resultado, "timestamp": ahora}
    return resultado

def obtener_tasa(base: str, destino: str):
    ahora = datetime.now()
    if destino in CACHE["tasas"]["value"] and ahora - CACHE["tasas"]["timestamp"] < CACHE_TTL:
        return CACHE["tasas"]["value"][destino]

    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        tasa = data['rates'].get(destino)
        CACHE["tasas"]["value"][destino] = tasa
        CACHE["tasas"]["timestamp"] = ahora
        return tasa
    except Exception as e:
        print(f"Error API open.er-api.com: {e}")
        return None

@app.get("/convertir_bob")
def convertir_bob(
    monto_bob: float = Query(1000, description="Monto en bolivianos a convertir")
):
    tc_bob_usd = obtener_promedio("BUY").get("promedio_bs")
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

    ahora = datetime.now()
    if CACHE["criptos"]["value"] and ahora - CACHE["criptos"]["timestamp"] < CACHE_TTL:
        precios_criptos = CACHE["criptos"]["value"]
    else:
        cripto_ids = ",".join(CRYPTO_MAP.values())
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={cripto_ids}&vs_currencies=usd"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            precios_criptos = r.json()
            CACHE["criptos"] = {"value": precios_criptos, "timestamp": ahora}
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
        "timestamp": ahora.isoformat()
    }
