from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, ROUND_HALF_UP
import os

# Configuración de precisión decimal
getcontext().prec = 28
RATE_Q = Decimal("0.0001")

# Ajuste global (resta %) en monedas FIAT excepto USD y EUR
FX_ADJ_FIAT = Decimal(os.getenv("FX_ADJ_FIAT", "0.995"))  # 0.995 = -0.5%

app = FastAPI(title="API Paralelo", version="1.3.2")

# Configuración CORS
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

# Caché
cache_binance = {"BUY": (None, None)}
cache_rates = {}
CACHE_EXP = timedelta(seconds=60)

# ----------- BINANCE P2P -----------
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

# ----------- AJUSTE GLOBAL MENOS USD/EUR -----------
def _ajuste_monedas(base: str, destino: str, rate: float) -> float:
    base = base.upper()
    destino = destino.upper()
    r = Decimal(str(rate))

    # Aplicar ajuste solo si ninguna de las dos es USD o EUR
    if not (destino in ["USD", "EUR"] or base in ["USD", "EUR"] and destino in ["USD", "EUR"]):
        r = (r * FX_ADJ_FIAT)

    return float(r.quantize(RATE_Q, rounding=ROUND_HALF_UP))

# ----------- API OPEN.ER-API -----------
def obtener_tasa(base: str, destino: str):
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
            rate = _ajuste_monedas(base, destino, raw)
            cache_rates[key] = {"rate": rate, "ts": now}
            return rate
        return None
    except Exception as e:
        print(f"Error API open.er-api.com: {e}")
        return None

# ----------- ENDPOINTS -----------

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
