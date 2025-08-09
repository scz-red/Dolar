from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime
from decimal import Decimal, getcontext

getcontext().prec = 12  # mayor precisión interna para evitar diferencias por redondeo

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

# ---------------- NO TOCAR: USD/BOB desde Binance P2P (tu lógica original) ----------------
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
    return {"promedio_bs": round(promedio, 4), "anuncios_validos": len(precios_validos)}

# ---------------- AJUSTE: USD -> Otras monedas con Yahoo Finance (fallback a open.er-api) ----------------
def obtener_tasa(base: str, destino: str):
    base = base.upper()
    destino = destino.upper()
    if base == destino:
        return 1.0

    def yf_usd_to(code: str):
        """Retorna USD->code desde Yahoo Finance como Decimal, o None si falla."""
        try:
            if code == "USD":
                return Decimal(1)
            sym = f"USD{code}=X"
            url = "https://query1.finance.yahoo.com/v7/finance/quote"
            r = requests.get(url, params={"symbols": sym}, timeout=10)
            r.raise_for_status()
            res = r.json().get("quoteResponse", {}).get("result", [])
            px = res[0].get("regularMarketPrice") if res else None
            return Decimal(str(px)) if px else None
        except Exception:
            return None

    # Casos directos con USD como base o destino
    if base == "USD":
        r = yf_usd_to(destino)
        if r:
            return float(r)

    if destino == "USD":
        r = yf_usd_to(base)
        if r:
            return float(Decimal(1) / r)

    # Cruce vía USD: base->USD->destino = (1 / (USD->base)) * (USD->destino)
    r_base = yf_usd_to(base)
    r_dest = yf_usd_to(destino)
    if r_base and r_dest:
        return float(r_dest / r_base)

    # Fallback (tu fuente anterior)
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data['rates'].get(destino)
    except Exception:
        return None

# --------------------------------- ENDPOINTS (SIN CAMBIOS) ---------------------------------
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

# --------- NUEVOS ENDPOINTS ABAJO (todos con BUY) ---------
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
    cotizaciones = {"USD": round(tc_usd_bob, 2)}
    for cod in monedas:
        if cod == "USD":
            continue
        tasa = obtener_tasa(cod, "USD")
        if tasa:
            cotizaciones[cod] = round(tc_usd_bob * tasa, 2)
        else:
            cotizaciones[cod] = "No disponible"
    return {
        "cotizaciones": cotizaciones,
        "timestamp": datetime.now().isoformat()
    }
