from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Dict, List, Optional
import time

getcontext().prec = 12  # precisión interna

app = FastAPI()

# CORS público, compatible con cualquier frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todos los orígenes (API pública)
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

# ================== FX (Yahoo bulk + fallback) ==================
YF_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
# Cache simple para todas las tasas pedidas en una ventana corta
_fx_cache: Dict[str, object] = {"t": 0.0, "rates": {}}  # {"t": epoch, "rates": {"USD":1.0,"EUR":0.92,...}}

def yf_bulk_rates_usd(codes: List[str], ttl: int = 120) -> Dict[str, Optional[float]]:
    """Obtiene USD->code para una lista de códigos en **un solo request**.
       Usa caché de ttl segundos para coherencia en la misma respuesta."""
    now = time.time()
    # Si ya tenemos las tasas y no expiraron, devuélvelas filtradas
    if _fx_cache["rates"] and (now - _fx_cache["t"] <= ttl):
        return {c: _fx_cache["rates"].get(c) for c in codes}

    symbols = []
    for c in codes:
        if c.upper() != "USD":
            symbols.append(f"USD{c.upper()}=X")

    rates: Dict[str, Optional[float]] = {"USD": 1.0}
    if symbols:
        r = requests.get(YF_URL, params={"symbols": ",".join(symbols)}, timeout=10)
        r.raise_for_status()
        results = r.json().get("quoteResponse", {}).get("result", [])
        by_symbol = {it.get("symbol"): it for it in results}
        for c in codes:
            cu = c.upper()
            if cu == "USD":
                rates["USD"] = 1.0
                continue
            sym = f"USD{cu}=X"
            px = by_symbol.get(sym, {}).get("regularMarketPrice")
            rates[cu] = float(px) if px is not None else None
    # guarda en caché
    _fx_cache["t"] = now
    _fx_cache["rates"] = rates.copy()
    return {c: rates.get(c.upper()) for c in codes}

def obtener_tasa(base: str, destino: str) -> Optional[float]:
    """Devuelve tasa base->destino. Prioriza Yahoo (bulk), fallback a open.er-api."""
    base = base.upper()
    destino = destino.upper()
    if base == destino:
        return 1.0

    # 1) Intento con snapshot Yahoo (bulk)
    if base == "USD":
        r = yf_bulk_rates_usd([destino]).get(destino)
        if r: return r
    elif destino == "USD":
        r = yf_bulk_rates_usd([base]).get(base)
        if r: return float(Decimal(1) / Decimal(str(r)))
    else:
        r_base = yf_bulk_rates_usd([base]).get(base)       # USD->base
        r_dest = yf_bulk_rates_usd([destino]).get(destino) # USD->dest
        if r_base and r_dest:
            # base->dest = (USD->dest) / (USD->base)
            return float(Decimal(str(r_dest)) / Decimal(str(r_base)))

    # 2) Fallback open.er-api.com
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data["rates"].get(destino)
    except Exception:
        return None

# ================== NO TOCAR: USD/BOB desde Binance P2P (tu lógica) ==================
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
    # Mantengo tu redondeo original a 2 decimales
    return {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios_validos)}

# ================== ENDPOINTS (sin cambios) ==================
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

    # Yahoo bulk para coherencia en todas las monedas
    codes = list(monedas.keys())
    rates = yf_bulk_rates_usd(codes)  # USD->code en un solo snapshot

    conversiones_fiat = {}
    for codigo, nombre in monedas.items():
        tasa = rates.get(codigo)
        conversiones_fiat[nombre] = round(usd * tasa, 2) if tasa else "No disponible"

    # Cripto
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
            conversiones_cripto[cripto] = round(usd / precio, 6) if precio else "No disponible"

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
            "output": f"{round(monto_bob, 2)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            "resultado": round(monto_bob, 2),
            "timestamp": datetime.now().isoformat()
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
            f"tasa_{moneda.lower()}_usd": tasa,
            "resultado": round(monto_bob, 2),
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

    # USD->code (Yahoo bulk) para un snapshot coherente
    rates = yf_bulk_rates_usd(monedas)
    cotizaciones = {"USD": round(tc_usd_bob, 2)}
    for cod in monedas:
        if cod == "USD":
            continue
        tasa_usd_a_cod = rates.get(cod)  # USD->cod
        if tasa_usd_a_cod:
            # BOB por 1 unidad de 'cod' = (BOB por USD) / (USD->cod)
            cotizaciones[cod] = round(tc_usd_bob / tasa_usd_a_cod, 2)
        else:
            cotizaciones[cod] = "No disponible"

    return {
        "cotizaciones": cotizaciones,
        "timestamp": datetime.now().isoformat()
    }
