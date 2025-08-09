from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, time
from datetime import datetime
from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Dict, List, Optional

# Precisión alta
getcontext().prec = 28

app = FastAPI()

# CORS
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
    "TRUMP": "trumpcoin",
}

# ====== helpers ======
CURRENCY_DECIMALS = {
    "USD": 2, "EUR": 2, "COP": 2, "ARS": 2, "CLP": 0,
    "BRL": 2, "PEN": 2, "PYG": 0, "MXN": 2, "CNY": 2,
}
RATE_Q = Decimal("0.0001")  # 4 decimales en TASA
DIFF_THRESHOLD = Decimal("0.005")  # 0.5% para decidir fuente

def fmt_amount(code: str, amount: Decimal):
    d = CURRENCY_DECIMALS.get(code.upper(), 2)
    q = Decimal(1).scaleb(-d)
    val = amount.quantize(q, rounding=ROUND_HALF_UP)
    return int(val) if d == 0 else float(val)

def _safe_float(x) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None

# ====== FX (Yahoo bulk + OpenER + selector) ======
YF_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
ER_URL = "https://open.er-api.com/v6/latest/"

_fx_cache: Dict[str, object] = {"t": 0.0, "rates": {}}  # USD->code (Decimal)

def yf_bulk_rates_usd(codes: List[str], ttl: int = 120) -> Dict[str, Optional[Decimal]]:
    """USD->code en un solo request. Prefiere cierre; redondea a 4 decimales. Con caché."""
    now = time.time()
    if _fx_cache["rates"] and (now - _fx_cache["t"] <= ttl):
        return {c: _fx_cache["rates"].get(c.upper()) for c in codes}

    rates: Dict[str, Optional[Decimal]] = {"USD": Decimal(1)}
    symbols = [f"USD{c.upper()}=X" for c in codes if c.upper() != "USD"]

    try:
        if symbols:
            r = requests.get(YF_URL, params={"symbols": ",".join(symbols)}, timeout=10)
            r.raise_for_status()
            results = r.json().get("quoteResponse", {}).get("result", [])
            by_symbol = {it.get("symbol"): it for it in results}
            for c in codes:
                cu = c.upper()
                if cu == "USD":
                    rates["USD"] = Decimal(1)
                    continue
                sym = f"USD{cu}=X"
                item = by_symbol.get(sym, {})
                px = item.get("regularMarketPreviousClose") or item.get("regularMarketPrice")
                rates[cu] = Decimal(str(px)).quantize(RATE_Q, rounding=ROUND_HALF_UP) if px is not None else None
    except Exception:
        for c in codes:
            if c.upper() not in rates:
                rates[c.upper()] = None

    _fx_cache["t"] = now
    _fx_cache["rates"] = rates.copy()
    return {c: rates.get(c.upper()) for c in codes}

def er_rate_usd_to(code: str) -> Optional[Decimal]:
    """Fallback: USD->code desde open.er-api.com; redondeado a 4 decimales."""
    try:
        r = requests.get(ER_URL + "USD", timeout=10)
        r.raise_for_status()
        val = r.json().get("rates", {}).get(code.upper())
        return Decimal(str(val)).quantize(RATE_Q, rounding=ROUND_HALF_UP) if val else None
    except Exception:
        return None

def pick_rate(code: str) -> Optional[Decimal]:
    """Elige la mejor USD->code comparando Yahoo vs OpenER; si difieren >0.5%, usa OpenER."""
    code = code.upper()
    t_yf = yf_bulk_rates_usd([code]).get(code)
    t_er = er_rate_usd_to(code)
    if t_yf and t_er:
        diff = (abs(t_yf - t_er) / t_er)
        return t_er if diff > DIFF_THRESHOLD else t_yf
    return t_yf or t_er

def obtener_tasa(base: str, destino: str) -> Optional[float]:
    """Tasa base->destino con selector de fuente y 4 decimales en TASA."""
    base = base.upper()
    destino = destino.upper()
    if base == destino:
        return 1.0

    if base == "USD":
        t = pick_rate(destino)
        return float(t) if t else None

    if destino == "USD":
        t = pick_rate(base)  # USD->base
        return float((Decimal(1) / t).quantize(RATE_Q, rounding=ROUND_HALF_UP)) if t else None

    # Cruce: (USD->dest) / (USD->base)
    t_base = pick_rate(base)
    t_dest = pick_rate(destino)
    if t_base and t_dest:
        cross = (t_dest / t_base).quantize(RATE_Q, rounding=ROUND_HALF_UP)
        return float(cross)
    return None

# ====== NO TOCAR: USD/BOB desde Binance P2P ======
def obtener_promedio(direccion: str):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    data = {
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": direccion,
        "page": 1,
        "rows": 10,
        "payTypes": [],
        "publisherType": None,
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
        precio = _safe_float(adv.get("price", 0))
        if precio and precio > 0:
            precios_validos.append(precio)
        if len(precios_validos) >= 5:
            break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    return {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios_validos)}

# ====== ENDPOINTS ======
@app.get("/convertir_bob")
def convertir_bob(monto_bob: float = Query(1000, description="Monto en bolivianos a convertir")):
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}

    tc_bob_usd = resultado_promedio.get("promedio_bs")
    if not tc_bob_usd:
        return {"error": "No se pudo obtener tipo de cambio paralelo."}

    usd_dec = Decimal(str(monto_bob)) / Decimal(str(tc_bob_usd))

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

    # tasas desde selector
    conversiones_fiat = {}
    for codigo, nombre in monedas.items():
        t = pick_rate(codigo)  # USD->codigo (Decimal)
        if not t:
            conversiones_fiat[nombre] = "No disponible"
            continue
        valor = usd_dec * t
        conversiones_fiat[nombre] = fmt_amount(codigo, valor)

    # Cripto (CoinGecko)
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
            conversiones_cripto["Tether (USDT)"] = fmt_amount("USD", usd_dec)
        else:
            px = precios_criptos.get(cripto_id, {}).get("usd")
            if px:
                val = (usd_dec / Decimal(str(px))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                conversiones_cripto[cripto] = float(val)
            else:
                conversiones_cripto[cripto] = "No disponible"

    return {
        "monto_bob": monto_bob,
        "tc_bob_usd": tc_bob_usd,
        "monto_usd": fmt_amount("USD", usd_dec),
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
    usd_dec = Decimal(str(monto_bob)) / Decimal(str(tc_bob_usd))
    if moneda == "USD":
        valor = usd_dec
    else:
        t = obtener_tasa("USD", moneda)
        if not t:
            return {"error": f"No se pudo obtener la tasa USD->{moneda}"}
        valor = usd_dec * Decimal(str(t))
    return {
        "input": f"{monto_bob} BOB",
        "output": f"{fmt_amount(moneda, valor)} {moneda}",
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
        monto_bob = Decimal(str(monto)) * Decimal(str(tc_usd_bob))
        return {
            "input": f"{monto} USD",
            "output": f"{fmt_amount('USD', monto_bob)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            "resultado": fmt_amount("USD", monto_bob),
            "timestamp": datetime.now().isoformat()
        }
    else:
        t = obtener_tasa(moneda, "USD")
        if not t:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        monto_usd = Decimal(str(monto)) * Decimal(str(t))
        monto_bob = monto_usd * Decimal(str(tc_usd_bob))
        return {
            "input": f"{monto} {moneda}",
            "output": f"{fmt_amount('USD', monto_bob)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": _safe_float(t),
            "resultado": fmt_amount('USD', monto_bob),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/cambio_bolivianos")
def cambio_bolivianos():
    monedas = ["USD", "EUR", "COP", "ARS", "CLP", "BRL", "PEN", "CNY", "PYG", "MXN"]
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"])}
    tc_usd_bob = Decimal(str(resultado_promedio.get("promedio_bs")))

    cotizaciones = {"USD": fmt_amount("USD", tc_usd_bob)}
    for cod in monedas:
        if cod == "USD":
            continue
        t = pick_rate(cod)  # USD->cod
        if t:
            bob_por_cod = tc_usd_bob / t
            cotizaciones[cod] = fmt_amount(cod, bob_por_cod)
        else:
            cotizaciones[cod] = "No disponible"

    return {
        "cotizaciones": cotizaciones,
        "timestamp": datetime.now().isoformat()
    }
