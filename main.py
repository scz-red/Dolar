from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta

app = FastAPI()

# CORS - Ajústalo para producción
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

MONEDAS_FIAT = {
    "USD": "Dólar estadounidense",
    "EUR": "Euro",
    "COP": "Peso colombiano",
    "ARS": "Peso argentino",
    "CLP": "Peso chileno",
    "BRL": "Real brasileño",
    "PEN": "Sol peruano",
    "CNY": "Yuan chino",
    "PYG": "Guaraní paraguayo",
    "MXN": "Peso mexicano"
}

# ---- CACHE SIMPLE EN MEMORIA ----
CACHE = {}
CACHE_TIMEOUT = timedelta(minutes=5)

def get_cache(key):
    data = CACHE.get(key)
    if data and datetime.now() < data["expiry"]:
        return data["value"]
    return None

def set_cache(key, value):
    CACHE[key] = {"value": value, "expiry": datetime.now() + CACHE_TIMEOUT}

# ---- BINANCE P2P (dólar paralelo) ----
def obtener_promedio_binance(direccion: str):
    cache_key = f"binance_{direccion}"
    cached = get_cache(cache_key)
    if cached:
        return cached
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
        return {"error": f"Error Binance: {str(e)}"}
    precios = []
    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        min_trans = adv.get("minSingleTransAmount", 0)
        if min_trans and float(min_trans) > 2000:
            continue
        precio = float(adv.get("price", 0))
        precios.append(precio)
        if len(precios) >= 5:
            break
    if not precios:
        return {"error": "No hay suficientes anuncios válidos."}
    promedio = sum(precios) / len(precios)
    res = {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios)}
    set_cache(cache_key, res)
    return res

# ---- FIAT RATES (cache) ----
def obtener_tasa(base: str, destino: str):
    cache_key = f"fiat_{base}_{destino}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        tasa = data['rates'].get(destino)
        if tasa:
            set_cache(cache_key, tasa)
        return tasa
    except Exception as e:
        return None

# ---- CRYPTO PRICES (cache) ----
def obtener_precios_cripto():
    cache_key = "cripto_usd"
    cached = get_cache(cache_key)
    if cached:
        return cached
    cripto_ids = ",".join(CRYPTO_MAP.values())
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cripto_ids}&vs_currencies=usd"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        precios = r.json()
        set_cache(cache_key, precios)
        return precios
    except Exception:
        return {}

# ----- ENDPOINTS -----

# BOB a todo (fiat + cripto)
@app.get("/convertir_bob")
def convertir_bob(monto_bob: float = Query(1000)):
    resultado = obtener_promedio_binance("BUY")
    if "error" in resultado:
        return {"error": resultado["error"]}
    tc_bob_usd = resultado["promedio_bs"]
    usd = monto_bob / tc_bob_usd
    conversiones_fiat = {}
    for codigo, nombre in MONEDAS_FIAT.items():
        tasa = obtener_tasa("USD", codigo)
        if tasa:
            valor = usd * tasa
            conversiones_fiat[nombre] = round(valor, 2)
        else:
            conversiones_fiat[nombre] = "No disponible"
    precios_criptos = obtener_precios_cripto()
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

# Inversa: USD/EUR/YUAN a BOB
@app.get("/convertir_a_bob")
def convertir_a_bob(monto: float = Query(...), moneda: str = Query(...)):
    moneda = moneda.upper()
    if moneda == "USD":
        resultado = obtener_promedio_binance("SELL")
        if "error" in resultado:
            return {"error": resultado["error"]}
        tc_usd_bob = resultado["promedio_bs"]
        monto_bob = monto * tc_usd_bob
        return {
            "monto": monto,
            "moneda": moneda,
            "monto_bob": round(monto_bob, 2),
            "tc_usd_bob": tc_usd_bob,
            "timestamp": datetime.now().isoformat()
        }
    else:
        tasa = obtener_tasa(moneda, "USD")
        if not tasa:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        resultado = obtener_promedio_binance("SELL")
        if "error" in resultado:
            return {"error": resultado["error"]}
        tc_usd_bob = resultado["promedio_bs"]
        monto_usd = monto * tasa
        monto_bob = monto_usd * tc_usd_bob
        return {
            "monto": monto,
            "moneda": moneda,
            "monto_bob": round(monto_bob, 2),
            "tc_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": tasa,
            "timestamp": datetime.now().isoformat()
        }

# Consulta rápida: ¿Cuánto es 1 USD, 1 EUR y 1 CNY (yuan) en bolivianos?
@app.get("/cambio_bolivianos")
def cambio_bolivianos():
    resultado = {}

    # USD a BOB
    r_usd = obtener_promedio_binance("SELL")
    if "error" in r_usd:
        resultado["USD"] = r_usd["error"]
    else:
        resultado["USD"] = round(r_usd["promedio_bs"], 2)

    # EUR a BOB
    tasa_eur_usd = obtener_tasa("EUR", "USD")
    if not tasa_eur_usd or "error" in r_usd:
        resultado["EUR"] = "No disponible"
    else:
        resultado["EUR"] = round(r_usd["promedio_bs"] * tasa_eur_usd, 2)

    # CNY (Yuan) a BOB
    tasa_cny_usd = obtener_tasa("CNY", "USD")
    if not tasa_cny_usd or "error" in r_usd:
        resultado["CNY"] = "No disponible"
    else:
        resultado["CNY"] = round(r_usd["promedio_bs"] * tasa_cny_usd, 2)

    return {
        "bolivianos_por_unidad": resultado,
        "fuente": "Binance P2P + Open Exchange Rates",
        "timestamp": datetime.now().isoformat()
    }

# Solo fiat
@app.get("/convertir_fiat")
def convertir_fiat(monto_usd: float = Query(...)):
    conversiones_fiat = {}
    for codigo, nombre in MONEDAS_FIAT.items():
        tasa = obtener_tasa("USD", codigo)
        if tasa:
            valor = monto_usd * tasa
            conversiones_fiat[nombre] = round(valor, 2)
        else:
            conversiones_fiat[nombre] = "No disponible"
    return {
        "monto_usd": monto_usd,
        "conversiones_fiat": conversiones_fiat,
        "timestamp": datetime.now().isoformat()
    }

# Solo cripto
@app.get("/convertir_cripto")
def convertir_cripto(monto_usd: float = Query(...)):
    precios_criptos = obtener_precios_cripto()
    conversiones_cripto = {}
    for cripto, cripto_id in CRYPTO_MAP.items():
        precio = precios_criptos.get(cripto_id, {}).get("usd")
        if precio:
            valor = monto_usd / precio
            conversiones_cripto[cripto] = round(valor, 6)
        else:
            conversiones_cripto[cripto] = "No disponible"
    return {
        "monto_usd": monto_usd,
        "conversiones_cripto": conversiones_cripto,
        "timestamp": datetime.now().isoformat()
    }

# Consulta simple: ¿cuánto es X de moneda a bolivianos?
@app.get("/cambio_a_bob")
def cambio_a_bob(moneda: str = Query(...), monto: float = Query(1)):
    moneda = moneda.upper()
    if moneda == "USD":
        resultado = obtener_promedio_binance("SELL")
        if "error" in resultado:
            return {"error": resultado["error"]}
        tc_usd_bob = resultado["promedio_bs"]
        monto_bob = monto * tc_usd_bob
        return {
            "input": f"{monto} {moneda}",
            "output": f"{round(monto_bob, 2)} BOB",
            "tasa": tc_usd_bob
        }
    else:
        tasa = obtener_tasa(moneda, "USD")
        if not tasa:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        resultado = obtener_promedio_binance("SELL")
        if "error" in resultado:
            return {"error": resultado["error"]}
        tc_usd_bob = resultado["promedio_bs"]
        monto_usd = monto * tasa
        monto_bob = monto_usd * tc_usd_bob
        return {
            "input": f"{monto} {moneda}",
            "output": f"{round(monto_bob, 2)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": tasa
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
