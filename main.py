from fastapi.middleware.cors import CORSMiddleware
import requests, time
from datetime import datetime
from decimal import Decimal, getcontext
from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Dict, List, Optional

getcontext().prec = 12  # mayor precisión interna
# Precisión alta para evitar errores acumulados
getcontext().prec = 28

app = FastAPI()

@@ -29,30 +30,41 @@
    "TRUMP": "trumpcoin",
}

# ================== FX (Yahoo bulk + fallback por moneda) ==================
YF_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
ER_URL = "https://open.er-api.com/v6/latest/"  # fallback

_fx_cache: Dict[str, object] = {"t": 0.0, "rates": {}}  # {"USD":1.0,"EUR":0.92,...}
# ================== Helpers de formato ==================
CURRENCY_DECIMALS = {
    "USD": 2, "EUR": 2, "COP": 2, "ARS": 2, "CLP": 0,
    "BRL": 2, "PEN": 2, "PYG": 0, "MXN": 2, "CNY": 2,
}
RATE_Q = Decimal("0.0001")  # 4 decimales en la TASA
def fmt_amount(code: str, amount: Decimal):
    d = CURRENCY_DECIMALS.get(code.upper(), 2)
    q = Decimal(1).scaleb(-d)
    val = amount.quantize(q, rounding=ROUND_HALF_UP)
    return int(val) if d == 0 else float(val)

def _safe_float(x) -> Optional[float]:
    try:
        if x is None: return None
        return float(x)
    except Exception:
        return None

def yf_bulk_rates_usd(codes: List[str], ttl: int = 120) -> Dict[str, Optional[float]]:
# ================== FX (Yahoo bulk + fallback) ==================
YF_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
ER_URL = "https://open.er-api.com/v6/latest/"

_fx_cache: Dict[str, object] = {"t": 0.0, "rates": {}}  # {"USD":1.0,"EUR":0.92,...}

def yf_bulk_rates_usd(codes: List[str], ttl: int = 120) -> Dict[str, Optional[Decimal]]:
    """
    Devuelve dict USD->code para una lista de códigos en un solo request.
    Usa caché corta. Nunca lanza excepción: si falla, retorna None por moneda.
    Devuelve USD->code para la lista codes en un solo request.
    Tasa redondeada a 4 decimales. Usa caché corta. Nunca lanza excepción.
    """
    now = time.time()
    # si la caché sirve, úsala
    if _fx_cache["rates"] and (now - _fx_cache["t"] <= ttl):
        # devuelve copia filtrada
        return {c: _fx_cache["rates"].get(c.upper()) for c in codes}

    rates: Dict[str, Optional[float]] = {"USD": 1.0}
    rates: Dict[str, Optional[Decimal]] = {"USD": Decimal(1)}
    symbols = [f"USD{c.upper()}=X" for c in codes if c.upper() != "USD"]

    try:
@@ -64,70 +76,64 @@ def yf_bulk_rates_usd(codes: List[str], ttl: int = 120) -> Dict[str, Optional[fl
            for c in codes:
                cu = c.upper()
                if cu == "USD":
                    rates["USD"] = 1.0
                    rates["USD"] = Decimal(1)
                    continue
                sym = f"USD{cu}=X"
                px = by_symbol.get(sym, {}).get("regularMarketPrice")
                rates[cu] = _safe_float(px)
                if px is not None:
                    # tasa con 4 decimales
                    rates[cu] = Decimal(str(px)).quantize(RATE_Q, rounding=ROUND_HALF_UP)
                else:
                    rates[cu] = None
    except Exception:
        # si Yahoo falla del todo, devolvemos None y luego haremos fallback por moneda
        for c in codes:
            if c.upper() not in rates:
                rates[c.upper()] = None

    # guarda snapshot en caché (aunque parcial)
    _fx_cache["t"] = now
    _fx_cache["rates"] = rates.copy()
    return {c: rates.get(c.upper()) for c in codes}

def er_rate_usd_to(code: str) -> Optional[float]:
    """Fallback: USD->code con open.er-api.com. No lanza excepción."""
def er_rate_usd_to(code: str) -> Optional[Decimal]:
    """Fallback: USD->code desde open.er-api.com, redondeado a 4 decimales."""
    try:
        r = requests.get(ER_URL + "USD", timeout=10)
        r.raise_for_status()
        return _safe_float(r.json().get("rates", {}).get(code.upper()))
        val = r.json().get("rates", {}).get(code.upper())
        return Decimal(str(val)).quantize(RATE_Q, rounding=ROUND_HALF_UP) if val else None
    except Exception:
        return None

def obtener_tasa(base: str, destino: str) -> Optional[float]:
    """
    Devuelve tasa base->destino. Prioriza Yahoo (bulk snapshot) y,
    si falta alguna moneda, cae a open.er-api por moneda.
    Tasa base->destino. Prioriza Yahoo (bulk snapshot) y, si falta, cae a open.er-api.
    Internamente usa Decimal y redondea la TASA a 4 decimales.
    """
    base = base.upper()
    destino = destino.upper()
    if base == destino:
        return 1.0

    # 1) Yahoo (bulk snapshot desde caché o nueva llamada)
    if base == "USD":
        tasa = yf_bulk_rates_usd([destino]).get(destino)
        if tasa: return tasa
        # fallback por moneda
        return er_rate_usd_to(destino)
        t = yf_bulk_rates_usd([destino]).get(destino) or er_rate_usd_to(destino)
        return float(t) if t else None

    if destino == "USD":
        tasa_usd_base = yf_bulk_rates_usd([base]).get(base)  # USD->base
        if tasa_usd_base:
            return float(Decimal(1) / Decimal(str(tasa_usd_base)))
        # fallback por moneda
        t = er_rate_usd_to(base)
        return float(Decimal(1) / Decimal(str(t))) if t else None

    # Cruce via USD: (USD->dest) / (USD->base)
    r_base = yf_bulk_rates_usd([base]).get(base) or er_rate_usd_to(base)
    r_dest = yf_bulk_rates_usd([destino]).get(destino) or er_rate_usd_to(destino)
    if r_base and r_dest:
        return float(Decimal(str(r_dest)) / Decimal(str(r_base)))
        t = yf_bulk_rates_usd([base]).get(base) or er_rate_usd_to(base)  # USD->base
        return float((Decimal(1) / t).quantize(RATE_Q, rounding=ROUND_HALF_UP)) if t else None

    # Cruce vía USD: (USD->dest) / (USD->base)
    t_base = yf_bulk_rates_usd([base]).get(base) or er_rate_usd_to(base)
    t_dest = yf_bulk_rates_usd([destino]).get(destino) or er_rate_usd_to(destino)
    if t_base and t_dest:
        cross = (t_dest / t_base).quantize(RATE_Q, rounding=ROUND_HALF_UP)
        return float(cross)
    return None

# ================== NO TOCAR: USD/BOB desde Binance P2P ==================
def obtener_promedio(direccion: str):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    data = {
        "asset": "USDT",
        "fiat": "BOB",
@@ -160,9 +166,10 @@ def obtener_promedio(direccion: str):
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    # Mantengo 2 decimales como tenías
    return {"promedio_bs": round(promedio, 2), "anuncios_validos": len(precios_validos)}

# ================== ENDPOINTS ==================
# ================== ENDPOINTS (sin cambios) ==================
@app.get("/convertir_bob")
def convertir_bob(monto_bob: float = Query(1000, description="Monto en bolivianos a convertir")):
    resultado_promedio = obtener_promedio("BUY")
@@ -173,7 +180,7 @@ def convertir_bob(monto_bob: float = Query(1000, description="Monto en boliviano
    if not tc_bob_usd:
        return {"error": "No se pudo obtener tipo de cambio paralelo."}

    usd = monto_bob / tc_bob_usd
    usd_dec = Decimal(str(monto_bob)) / Decimal(str(tc_bob_usd))

    monedas = {
        "USD": "Dólar estadounidense",
@@ -188,19 +195,18 @@ def convertir_bob(monto_bob: float = Query(1000, description="Monto en boliviano
        "CNY": "Yuan chino",
    }

    # Snapshot Yahoo en bulk (con fallback interno si falta alguna)
    # Snapshot coherente para todas las monedas
    codes = list(monedas.keys())
    rates = yf_bulk_rates_usd(codes)

    conversiones_fiat = {}
    for codigo, nombre in monedas.items():
        tasa = rates.get(codigo)
        if tasa is None:  # fallback individual a open.er-api si faltó en Yahoo
            if codigo == "USD":
                tasa = 1.0
            else:
                tasa = er_rate_usd_to(codigo)
        conversiones_fiat[nombre] = round(usd * tasa, 2) if tasa else "No disponible"
        t = rates.get(codigo) or er_rate_usd_to(codigo)
        if not t:
            conversiones_fiat[nombre] = "No disponible"
            continue
        valor = usd_dec * t  # USD -> moneda, tasa ya con 4 decimales
        conversiones_fiat[nombre] = fmt_amount(codigo, valor)

    # Cripto (CoinGecko)
    cripto_ids = ",".join(CRYPTO_MAP.values())
@@ -215,18 +221,18 @@ def convertir_bob(monto_bob: float = Query(1000, description="Monto en boliviano
    conversiones_cripto = {}
    for cripto, cripto_id in CRYPTO_MAP.items():
        if cripto == "USDT":
            conversiones_cripto["Tether (USDT)"] = round(usd, 2)
            conversiones_cripto["Tether (USDT)"] = fmt_amount("USD", usd_dec)
        else:
            precio = precios_criptos.get(cripto_id, {}).get("usd")
            conversiones_cripto[cripto] = round(usd / precio, 6) if precio else "No disponible"
            px = precios_criptos.get(cripto_id, {}).get("usd")
            conversiones_cripto[cripto] = float((usd_dec / Decimal(str(px))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)) if px else "No disponible"

    return {
        "monto_bob": monto_bob,
        "tc_bob_usd": tc_bob_usd,
        "monto_usd": round(usd, 2),
        "monto_usd": fmt_amount("USD", usd_dec),
        "conversiones_fiat": conversiones_fiat,
        "conversiones_cripto": conversiones_cripto,
        "timestamp": datetime.now().isoformat(),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/convertir_bob_moneda")
@@ -236,19 +242,19 @@ def convertir_bob_moneda(moneda: str = Query(...), monto_bob: float = Query(1000
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}
    tc_bob_usd = resultado_promedio.get("promedio_bs")
    usd = monto_bob / tc_bob_usd
    usd_dec = Decimal(str(monto_bob)) / Decimal(str(tc_bob_usd))
    if moneda == "USD":
        valor = usd
        valor = usd_dec
    else:
        tasa = obtener_tasa("USD", moneda)
        if not tasa:
        t = obtener_tasa("USD", moneda)
        if not t:
            return {"error": f"No se pudo obtener la tasa USD->{moneda}"}
        valor = usd * tasa
        valor = usd_dec * Decimal(str(t))
    return {
        "input": f"{monto_bob} BOB",
        "output": f"{round(valor, 2)} {moneda}",
        "output": f"{fmt_amount(moneda, valor)} {moneda}",
        "tc_bob_usd": tc_bob_usd,
        "timestamp": datetime.now().isoformat(),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/cambio_a_bob")
@@ -259,27 +265,27 @@ def cambio_a_bob(moneda: str = Query(...), monto: float = Query(1)):
        return {"error": resultado_promedio["error"]}
    tc_usd_bob = resultado_promedio.get("promedio_bs")
    if moneda == "USD":
        monto_bob = monto * tc_usd_bob
        monto_bob = Decimal(str(monto)) * Decimal(str(tc_usd_bob))
        return {
            "input": f"{monto} USD",
            "output": f"{round(monto_bob, 2)} BOB",
            "output": f"{fmt_amount('USD', monto_bob)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            "resultado": round(monto_bob, 2),
            "timestamp": datetime.now().isoformat(),
            "resultado": fmt_amount("USD", monto_bob),
            "timestamp": datetime.now().isoformat()
        }
    else:
        tasa = obtener_tasa(moneda, "USD")
        if not tasa:
        t = obtener_tasa(moneda, "USD")
        if not t:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        monto_usd = monto * tasa
        monto_bob = monto_usd * tc_usd_bob
        monto_usd = Decimal(str(monto)) * Decimal(str(t))
        monto_bob = monto_usd * Decimal(str(tc_usd_bob))
        return {
            "input": f"{monto} {moneda}",
            "output": f"{round(monto_bob, 2)} BOB",
            "output": f"{fmt_amount('USD', monto_bob)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": tasa,
            "resultado": round(monto_bob, 2),
            "timestamp": datetime.now().isoformat(),
            f"tasa_{moneda.lower()}_usd": _safe_float(t),
            "resultado": fmt_amount('USD', monto_bob),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/cambio_bolivianos")
@@ -288,17 +294,22 @@ def cambio_bolivianos():
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}
    tc_usd_bob = resultado_promedio.get("promedio_bs")
    tc_usd_bob = Decimal(str(resultado_promedio.get("promedio_bs")))

    rates = yf_bulk_rates_usd(monedas)
    cotizaciones = {"USD": round(tc_usd_bob, 2)}

    cotizaciones = {"USD": float(tc_usd_bob.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}
    for cod in monedas:
        if cod == "USD":
            continue
        tasa = rates.get(cod) or er_rate_usd_to(cod)  # USD->cod
        cotizaciones[cod] = round(tc_usd_bob / tasa, 2) if tasa else "No disponible"
        t = rates.get(cod) or er_rate_usd_to(cod)  # USD->cod
        if t:
            bob_por_cod = tc_usd_bob / t
            cotizaciones[cod] = fmt_amount(cod, bob_por_cod)
        else:
            cotizaciones[cod] = "No disponible"

    return {
        "cotizaciones": cotizaciones,
        "timestamp": datetime.now().isoformat(),
        "timestamp": datetime.now().isoformat()
    }
