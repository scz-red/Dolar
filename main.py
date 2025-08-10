from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, ROUND_HALF_UP
import os

# --- Precisión alta ---
getcontext().prec = 28
RATE_Q = Decimal("0.0001")                 # 4 decimales en TASA
FX_ADJ = Decimal(os.getenv("FX_ADJ", "0.9935"))  # -0.5% por defecto (0.995). Cambia por ENV si quieres.

app = FastAPI(title="API Paralelo", version="1.3")

# CORS para cualquier frontend
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

# --- Caché simple en RAM ---
cache_binance = {"BUY": (None, None)}
cache_rates = {}  # key: "BASE-DEST" -> {"rate": float, "ts": datetime}
CACHE_EXP = timedelta(seconds=60)

# ------------------- Binance P2P (NO TOCAR) -------------------
def obtener_promedio(direccion: str):
    now = datetime.now()
    valor, ts = cache_binance.get(direccion, (None, None))
    if valor and ts and (now - ts) < CACHE_EXP:
        return valor

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
        return {"error": f"Error Binance: {str(e)}"}

    precios_validos = []
    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        min_trans = adv.get("minSingleTransAmount", 0)
        if min_trans and float(min_trans) > 2000:
            continue
        precio = float(adv.get("price", 0))
        if precio > 0:
            precios_validos.append(precio)
        if len(precios_validos) >= 5:
            break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    result = {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios_validos)}
    cache_binance[direccion] = (result, now)
    return result

# ------------------- FX (open.er-api) con ajuste -------------------
def _ajusta_tasa(rate: float) -> float:
    """Redondea la tasa a 4 decimales y aplica calibración anti-inflado."""
    r = Decimal(str(rate)).quantize(RATE_Q, rounding=ROUND_HALF_UP)
    r = (r * FX_ADJ).quantize(RATE_Q, rounding=ROUND_HALF_UP)
    return float(r)

def obtener_tasa(base: str, destino: str):
    """Tasa base->destino desde open.er-api + redondeo 4d + calibración (-0.5% por defecto)."""
    base = base.upper()
    destino = destino.upper()
    key = f"{base}-{destino}"

    now = datetime.now()
    entry = cache_rates.get(key)
    if entry and (now - entry['ts']) < CACHE_EXP:
        return entry['rate']

    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        raw = data['rates'].get(destino)
        if raw:
            rate = _ajusta_tasa(raw)
            cache_rates[key] = {"rate": rate, "ts": now}
            return rate
        return None
    except Exception as e:
        print(f"Error API open.er-api.com: {e}")
        return None

# ------------------- ENDPOINTS -------------------
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
        tasa = obtener_tasa("USD", codigo)  # USD -> codigo (ajustada)
        if tasa:
            valor = usd * tasa
            conversiones_fiat[nombre] = round(valor, 2)
        else:
            conversiones_fiat[nombre] = "No disponible"

    # Cripto (CoinGecko) con User-Agent para evitar bloqueos
    cripto_ids = ",".join(CRYPTO_MAP.values())
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        headers = {"User-Agent": "paralelo-bob/1.0 (+contacto)"}
        r = requests.get(url, params={"ids": cripto_ids, "vs_currencies": "usd"}, headers=headers, timeout=15)
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
        tasa = obtener_tasa("USD", moneda)
        if not tasa:
            return {"error": f"No se pudo obtener la tasa USD->{moneda}"}
        valor = usd * tasa
    return {
        "input": f"{monto_bob} BOB",
        "output": f"{round(valor, 2)} {moneda}",
        "tc_bob_usd": tc_bob_usd,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/cambio_a_bob")
def cambio_a_bob(moneda: str = Query(...), monto: float = Query(1)):
    moneda = moneda.upper()
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}
    tc_usd_bob = resultado_promedio.get("promedio_bs")
    if moneda == "USD":
        monto_bob = monto * tc_usd_bob
        return {
            "input": f"{monto} USD",
            "resultado": round(monto_bob, 2),
            "tasa_usd_bob": tc_usd_bob,
            "timestamp": datetime.now().isoformat()
        }
    else:
        tasa = obtener_tasa(moneda, "USD")  # moneda -> USD (ajustada)
        if not tasa:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        monto_usd = monto * tasa
        monto_bob = monto_usd * tc_usd_bob
        return {
            "input": f"{monto} {moneda}",
            "resultado": round(monto_bob, 2),
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": tasa,
            "timestamp": datetime.now().isoformat()
        }

@app.get("/cambio_bolivianos")
def cambio_bolivianos():
    monedas = ["USD", "EUR", "COP", "ARS", "CLP", "BRL", "PEN", "CNY", "PYG", "MXN"]
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}
    tc_usd_bob = resultado_promedio.get("promedio_bs")
    cotizaciones = {"USD": round(tc_usd_bob, 2)}
    for cod in monedas:
        if cod == "USD":
            continue
        tasa = obtener_tasa(cod, "USD")  # cod -> USD (ajustada)
        if tasa:
            cotizaciones[cod] = round(tc_usd_bob * tasa, 2)  # BOB por 1 unidad de 'cod'
        else:
            cotizaciones[cod] = "No disponible"
    return {
        "cotizaciones_bolivianos": cotizaciones,
        "timestamp": datetime.now().isoformat()
    }
