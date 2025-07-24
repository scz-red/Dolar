from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta

app = FastAPI()

# CORS - Puedes restringir esto en producción
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monedas soportadas
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
    except Exception:
        return None

# ------ ENDPOINTS PRINCIPALES ------

# 1. Convertir de moneda extranjera a BOB (bolivianos)
@app.get("/cambio_a_bob")
def cambio_a_bob(moneda: str = Query(..., description="Código de moneda (ej: USD, EUR, BRL, CNY)"), monto: float = Query(1)):
    moneda = moneda.upper()
    resultado = obtener_promedio_binance("SELL")
    if "error" in resultado:
        return {"error": resultado["error"]}
    tc_usd_bob = resultado["promedio_bs"]

    if moneda == "USD":
        monto_bob = monto * tc_usd_bob
        return {
            "input": f"{monto} USD",
            "output": f"{round(monto_bob, 2)} BOB",
            "tasa_usd_bob": tc_usd_bob
        }
    else:
        tasa = obtener_tasa(moneda, "USD")
        if not tasa:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        monto_usd = monto * tasa
        monto_bob = monto_usd * tc_usd_bob
        return {
            "input": f"{monto} {moneda}",
            "output": f"{round(monto_bob, 2)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": tasa
        }

# 2. Convertir de BOB a moneda extranjera
@app.get("/cambio_desde_bob")
def cambio_desde_bob(moneda: str = Query(..., description="Código de moneda (ej: USD, EUR, BRL, CNY)"), monto: float = Query(1)):
    moneda = moneda.upper()
    resultado = obtener_promedio_binance("BUY")
    if "error" in resultado:
        return {"error": resultado["error"]}
    tc_bob_usd = resultado["promedio_bs"]

    usd = monto / tc_bob_usd
    if moneda == "USD":
        return {
            "input": f"{monto} BOB",
            "output": f"{round(usd, 2)} USD",
            "tasa_bob_usd": tc_bob_usd
        }
    else:
        tasa = obtener_tasa("USD", moneda)
        if not tasa:
            return {"error": f"No se pudo obtener la tasa USD->{moneda}"}
        valor = usd * tasa
        return {
            "input": f"{monto} BOB",
            "output": f"{round(valor, 2)} {moneda}",
            "tasa_bob_usd": tc_bob_usd,
            f"tasa_usd_{moneda.lower()}": tasa
        }

# 3. Consulta rápida (todos a la vez): USD, EUR, BRL, CNY, ARS, COP, PEN, CLP, MXN, PYG
@app.get("/cambio_bolivianos")
def cambio_bolivianos():
    resultado = {}
    r_usd = obtener_promedio_binance("SELL")
    if "error" in r_usd:
        return {"error": r_usd["error"]}

    tc_usd_bob = r_usd["promedio_bs"]
    resultado["USD"] = round(tc_usd_bob, 2)

    # Resto de monedas
    for cod in MONEDAS_FIAT:
        if cod == "USD":
            continue
        tasa = obtener_tasa(cod, "USD")
        if tasa:
            resultado[cod] = round(tc_usd_bob * tasa, 2)
        else:
            resultado[cod] = "No disponible"

    return {
        "bolivianos_por_unidad": resultado,
        "fuente": "Binance P2P + Open Exchange Rates",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
