from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta
import time

app = FastAPI(title="API Paralelo", version="1.4")

# CORS global para frontend
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

cache_binance = {"BUY": (None, None)}
cache_rates = {}
CACHE_EXP = timedelta(seconds=60)

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
        precios_validos.append(precio)
        if len(precios_validos) >= 5:
            break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    result = {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios_validos)}
    cache_binance[direccion] = (result, now)
    return result

def obtener_tasa(base: str, destino: str):
    key = f"{base}-{destino}"
    now = datetime.now()
    entry = cache_rates.get(key)
    if entry and (now - entry['ts']) < CACHE_EXP:
        return entry['rate']
    try:
        url = f"https://api.exchangerate.host/convert?from={base}&to={destino}&amount=1"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        rate = data.get('result', None)
        if rate:
            cache_rates[key] = {"rate": rate, "ts": now}
        return rate
    except Exception as e:
        print(f"Error API exchangerate.host: {e}")
        return None

def obtener_precios_criptos(cripto_ids):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(cripto_ids)}&vs_currencies=usd"
    for intento in range(3):
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()
            if data:
                return data
        except Exception as e:
            if intento == 2:
                print(f"Error CoinGecko: {e}")
            time.sleep(0.5)
    return {}

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

    # --- FIAT ---
    conversiones_fiat = {}
    for codigo, nombre in monedas.items():
        tasa = obtener_tasa("USD", codigo)  # SIEMPRE USD -> moneda destino
        if tasa:
            valor = usd * tasa
            conversiones_fiat[nombre] = round(valor, 2)
        else:
            conversiones_fiat[nombre] = "No disponible"

    # --- CRIPTO ---
    cripto_ids = list(CRYPTO_MAP.values())
    precios_criptos = obtener_precios_criptos(cripto_ids)

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
        tasa = obtener_tasa("USD", moneda)
        if not tasa:
            return {"error": f"No se pudo obtener la tasa USD->{moneda}"}
        monto_usd = monto / tasa  # Invertimos la operación: monto en moneda / tasa USD->moneda = monto en USD
        monto_bob = monto_usd * tc_usd_bob
        return {
            "input": f"{monto} {moneda}",
            "resultado": round(monto_bob, 2),
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_usd_{moneda.lower()}": tasa,
            "timestamp": datetime.now().isoformat()
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
    cotizaciones = {"USD": round(tc_usd_bob, 2)}
    for cod in monedas:
        if cod == "USD":
            continue
        tasa = obtener_tasa("USD", cod)  # SIEMPRE USD -> moneda destino
        if tasa:
            cotizaciones[cod] = round(tc_usd_bob * tasa, 2)
        else:
            cotizaciones[cod] = "No disponible"
    return {
        "cotizaciones_bolivianos": cotizaciones,
        "timestamp": datetime.now().isoformat()
    }
