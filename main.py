from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, time
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Dict, List, Optional
import threading

# Configuración de precisión decimal
getcontext().prec = 28

app = FastAPI()

# CORS público
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mapeo de criptomonedas
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

# ================== Helpers de formato ==================
CURRENCY_DECIMALS = {
    "USD": 2, "EUR": 2, "COP": 2, "ARS": 2, "CLP": 0,
    "BRL": 2, "PEN": 2, "PYG": 0, "MXN": 2, "CNY": 2,
}
RATE_Q = Decimal("0.0001")  # 4 decimales para tasas

def fmt_amount(code: str, amount: Decimal):
    d = CURRENCY_DECIMALS.get(code.upper(), 2)
    q = Decimal(1).scaleb(-d)
    val = amount.quantize(q, rounding=ROUND_HALF_UP)
    return int(val) if d == 0 else float(val)

def _safe_float(x) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None

# ================== Gestor de Tasas Fiat Mejorado ==================
class FiatRateManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_rates()
        return cls._instance
    
    def _init_rates(self):
        self.adjustment_factors = {
            "COP": Decimal("1.10"),  # 2% de ajuste para COP
            "ARS": Decimal("1.01"),  # 5% de ajuste para ARS
            "CLP": Decimal("1.01"),
            "BRL": Decimal("1.005"),
            "PEN": Decimal("1.01"),
            "PYG": Decimal("1.01"),
            "MXN": Decimal("1.005"),
            "CNY": Decimal("1.0")
        }
    
    def get_adjusted_rate(self, currency: str) -> Optional[Decimal]:
        currency = currency.upper()
        if currency == "USD":
            return Decimal(1)
            
        # 1. Primero intentamos con Yahoo Finance
        yf_rate = self._get_yahoo_rate(currency)
        if yf_rate:
            return self._apply_adjustment(currency, yf_rate)
            
        # 2. Fallback a open.er-api.com
        er_rate = self._get_er_rate(currency)
        if er_rate:
            return self._apply_adjustment(currency, er_rate)
            
        return None
    
    def _get_yahoo_rate(self, currency: str) -> Optional[Decimal]:
        try:
            url = "https://query1.finance.yahoo.com/v7/finance/quote"
            params = {"symbols": f"USD{currency}=X"}
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            result = r.json().get("quoteResponse", {}).get("result", [{}])[0]
            rate = result.get("regularMarketPrice")
            return Decimal(str(rate)).quantize(RATE_Q) if rate else None
        except Exception:
            return None
    
    def _get_er_rate(self, currency: str) -> Optional[Decimal]:
        try:
            url = "https://open.er-api.com/v6/latest/USD"
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            rate = r.json().get("rates", {}).get(currency)
            return Decimal(str(rate)).quantize(RATE_Q) if rate else None
        except Exception:
            return None
    
    def _apply_adjustment(self, currency: str, rate: Decimal) -> Decimal:
        factor = self.adjustment_factors.get(currency, Decimal("1.0"))
        adjusted = rate * factor
        return adjusted.quantize(RATE_Q, rounding=ROUND_HALF_UP)

fiat_rate_manager = FiatRateManager()

# ================== Binance P2P (NO MODIFICADO) ==================
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

# ================== ENDPOINTS (MISMOS QUE ANTES) ==================
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

    conversiones_fiat = {}
    for codigo, nombre in monedas.items():
        if codigo == "USD":
            valor = usd_dec
        else:
            tasa = fiat_rate_manager.get_adjusted_rate(codigo)
            if not tasa:
                conversiones_fiat[nombre] = "No disponible"
                continue
            valor = usd_dec * tasa
            
        conversiones_fiat[nombre] = fmt_amount(codigo, valor)

    # Criptomonedas (CoinGecko)
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
            conversiones_cripto["Tether (USDT)"] = fmt_amount("USD", usd_dec)
        else:
            px = precios_criptos.get(cripto_id, {}).get("usd")
            conversiones_cripto[cripto] = float((usd_dec / Decimal(str(px))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)) if px else "No disponible"

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
        tasa = fiat_rate_manager.get_adjusted_rate(moneda)
        if not tasa:
            return {"error": f"No se pudo obtener la tasa USD->{moneda}"}
        valor = usd_dec * tasa
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
        tasa = fiat_rate_manager.get_adjusted_rate(moneda)
        if not tasa:
            return {"error": f"No se pudo obtener la tasa {moneda}->USD"}
        monto_usd = Decimal(str(monto)) * (Decimal(1) / tasa)
        monto_bob = monto_usd * Decimal(str(tc_usd_bob))
        return {
            "input": f"{monto} {moneda}",
            "output": f"{fmt_amount('USD', monto_bob)} BOB",
            "tasa_usd_bob": tc_usd_bob,
            f"tasa_{moneda.lower()}_usd": float(tasa),
            "resultado": fmt_amount('USD', monto_bob),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/cambio_bolivianos")
def cambio_bolivianos():
    monedas = ["USD", "EUR", "COP", "ARS", "CLP", "BRL", "PEN", "CNY", "PYG", "MXN"]
    resultado_promedio = obtener_promedio("BUY")
    if "error" in resultado_promedio:
        return {"error": resultado_promedio["error"]}
    tc_usd_bob = Decimal(str(resultado_promedio.get("promedio_bs")))

    cotizaciones = {"USD": float(tc_usd_bob.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}
    for cod in monedas:
        if cod == "USD":
            continue
        tasa = fiat_rate_manager.get_adjusted_rate(cod)
        if tasa:
            bob_por_cod = tc_usd_bob / tasa
            cotizaciones[cod] = fmt_amount(cod, bob_por_cod)
        else:
            cotizaciones[cod] = "No disponible"

    return {
        "cotizaciones": cotizaciones,
        "timestamp": datetime.now().isoformat()
    }
