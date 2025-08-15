from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime
import time

app = FastAPI()

# ================== CONFIG (una sola línea para el descuento) ==================
DESCUENTO_FIAT = 0.001  # 0.10% a todas las FIAT excepto USD y EUR

# CORS público
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

# ========= CACHÉ SIMPLE (TTL 60s) =========
CACHE = {}
TTL = 60

def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    if time.time() - item["t"] <= TTL:
        return item["v"]
    return None

def cache_set(key, value):
    CACHE[key] = {"v": value, "t": time.time()}

# ========= HELPERS DE TASAS =========
def obtener_todas_tasas(base: str):
    key = f"rates:{base.upper()}"
    cached = cache_get(key)
    if cached:
        return cached
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        rates = r.json().get("rates", {})
        cache_set(key, rates)
        return rates
    except Exception as e:
        print(f"Error API open.er-api.com: {e}")
        return {}

def obtener_tasa(base: str, destino: str):
    rates = obtener_todas_tasas(base)
    return rates.get(destino)

# ========= BINANCE P2P =========
def obtener_promedio(direccion: str):
    key = f"binance:{direccion}"
    cached = cache_get(key)
    if cached:
        return cached

    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
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
        adv = anuncio.get("adv", {}) or {}
        min_trans = adv.get("minSingleTransAmount", 0)
        try:
            if min_trans and float(min_trans) > 2000:
                continue
        except (TypeError, ValueError):
            pass

        try:
            precio = float(adv.get("price", 0) or 0)
        except (TypeError, ValueError):
            continue

        if precio > 0:
            precios_validos.append(precio)
            if len(precios_validos) >= 5:
                break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    result = {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios_validos)}
    cache_set(key, result)
    return result

# ========= ENDPOINTS =========
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
        "EUR": "Euro",
        "COP": "Peso colombiano",
        "ARS": "Peso argentino",
        "CLP": "Peso chileno",
        "BRL": "Real brasileño",
        "PEN": "Sol peruano",
        "PYG": "Guaraní paraguayo",
        "MXN": "Peso mexicano",
        "CNY": "Yuan chino",
    }

    rates_usd = obtener_todas_tasas("USD")
    conversiones_fiat = {}
    for codigo, nombre in monedas.items():
        if codigo == "USD":
            conversiones_fiat[nombre] = round(usd, 2)
            continue
        tasa = rates_usd.get(codigo)
        if tasa:
            valor = usd * tasa
            if codigo not in ("USD", "EUR"):
                valor *= (1 - DESCUENTO_FIAT)
            # COP sin decimales; resto 2 decimales
            conversiones_fiat[nombre] = round(valor, 0) if codigo == "COP" else round(valor, 2)
        else:
            conversiones_fiat[nombre] = "No disponible"

    cripto_ids = ",".join(CRYPTO_MAP.values())
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cripto_ids}&vs_currencies=usd"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        precios_criptos = r.json()
    except Exception:
        precios_criptos = {}

    conversiones_cripto = {}
    for cripto, cripto_id in CRYPTO_MAP.items():
        if cripto == "USDT":
            conversiones_cripto["Tether (USDT)"] = round(usd, 2)
        else:
            precio = precios_criptos.get(cripto_id, {}).get("usd")
            if precio:
                conversiones_cripto[cripto] = round(usd / precio, 6)
            else:
                conversiones_cripto[cripto] = "No disponible"

    ts = datetime.now().isoformat()
    return {
        "monto_bob": monto_bob,
        "tc_bob_usd": tc_bob_usd,
        "monto_usd": round(usd, 2),
        "conversiones_fiat": conversiones_fiat,
        "conversiones_cripto": conversiones_cripto,
        "timestamp": ts,
        "input": f"{monto_bob} BOB",
        "output": "ver conversiones",
        "resultado": {"USD": round(usd, 2), "FIAT": conversiones_fiat, "CRYPTO": conversiones_cripto}
    }

@app.get("/convertir_bob_moneda")
def convertir_bob_moneda(moneda: str = Query(...), monto_bob: float = Query(1000)):
    moneda = moneda.upper()
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}
    tc_bob_usd = resultado_promedio.get("promedio_bs")
    usd = monto_bob / tc_bob_usd

    if moneda == "USD":
        valor = usd
    else:
        rates_usd = obtener_todas_tasas("USD")
        tasa = rates_usd.get(moneda)
        if not tasa:
            return {"error": f"No se pudo obtener la tasa USD->{moneda}"}
        valor = usd * tasa
        if moneda not in ("USD", "EUR"):
            valor *= (1 - DESCUENTO_FIAT)

    # Redondeo especial para COP
    valor_redondeado = round(valor, 0) if moneda == "COP" else round(valor, 2)

    ts = datetime.now().isoformat()
    return {
        "input": f"{monto_bob} BOB",
        "output": f"{valor_redondeado} {moneda}",
        "resultado": valor_redondeado,
        "tc_bob_usd": tc_bob_usd,
        "timestamp": ts
    }

@app.get("/cambio_a_bob")
def cambio_a_bob(moneda: str = Query(...), monto: float = Query(1)):
    moneda = moneda.upper()
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}

    tc_usd_bob = resultado_promedio.get("promedio_bs")
    ts = datetime.now().isoformat()

    if moneda == "USD":
        monto_bob = monto * tc_usd_bob
        return {
            "input": f"{monto} USD",
            "output": f"{round(monto_bob, 2)} BOB",
            "resultado": round(monto_bob, 2),
            "tasa_usd_bob": tc_usd_bob,
            "timestamp": ts
        }
    else:
        rates = obtener_todas_tasas(moneda)
        tasa = rates.get("USD")
        if not tasa:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        monto_usd = monto * tasa
        monto_bob = monto_usd * tc_usd_bob
        return {
            "input": f"{monto} {moneda}",
            "output": f"{round(monto_bob, 2)} BOB",
            "resultado": round(monto_bob, 2),
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": tasa,
            "timestamp": ts
        }

@app.get("/cambio_bolivianos")
def cambio_bolivianos():
    monedas = [
        "USD", "EUR", "COP", "ARS", "CLP",
        "BRL", "PEN", "CNY", "PYG", "MXN"
    ]
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}
    tc_usd_bob = resultado_promedio.get("promedio_bs")

    rates_usd = obtener_todas_tasas("USD")
    cotizaciones = {"USD": round(tc_usd_bob, 2)}
    for cod in monedas:
        if cod == "USD":
            continue
        tasa_usd_cod = rates_usd.get(cod)
        if tasa_usd_cod:
            valor = tc_usd_bob * tasa_usd_cod
            if cod not in ("USD", "EUR"):
                valor *= (1 - DESCUENTO_FIAT)
            # COP sin decimales; resto 2 decimales
            cotizaciones[cod] = round(valor, 0) if cod == "COP" else round(valor, 2)
        else:
            cotizaciones[cod] = "No disponible"

    ts = datetime.now().isoformat()
    return {
        "cotizaciones": cotizaciones,
        "input": "1 unidad de cada moneda",
        "output": "BOB por unidad",
        "resultado": cotizaciones,
        "timestamp": ts
    }
