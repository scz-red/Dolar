from fastapi import FastAPI, Query
import requests
from datetime import datetime

app = FastAPI()

HEADERS = {
    "Content-Type": "application/json"
}

# Función para obtener promedio en Binance P2P
def obtener_promedio(direccion: str):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    data = {
        "page": 1,
        "rows": 20,
        "payTypes": [],
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": direccion.upper()
    }
    try:
        response = requests.post(url, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status()
        anuncios = response.json().get("data", [])
    except Exception as e:
        return {
            "error": "Error al consultar Binance",
            "detalle": str(e),
            "timestamp": datetime.now().isoformat()
        }

    precios_validos = []
    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        restricciones = adv.get("minSingleTransAmount", 0)
        if restricciones and float(restricciones) > 2000:
            continue
        precio = float(adv.get("price", 0))
        precios_validos.append(precio)
        if len(precios_validos) == 5:
            break

    if not precios_validos:
        return {
            "error": "No hay suficientes anuncios válidos.",
            "direccion": direccion.lower(),
            "timestamp": datetime.now().isoformat()
        }

    promedio = sum(precios_validos) / len(precios_validos)
    return {
        "direccion": direccion.lower(),
        "promedio_bs": round(promedio, 2),
        "anuncios_validos": len(precios_validos),
        "timestamp": datetime.now().isoformat()
    }

# Función para obtener tasas de divisas (USD a otra moneda)
def obtener_tasa(base: str, destino: str):
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data['rates'].get(destino)
    except Exception as e:
        print(f"Error API open.er-api.com: {e}")
        return None

# Función para obtener precio de criptomonedas con CoinGecko
def obtener_precio_coingecko(cripto_id: str):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cripto_id}&vs_currencies=usd"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get(cripto_id, {}).get('usd')
    except Exception as e:
        print(f"Error CoinGecko: {e}")
        return None

# Mapeo para criptos: símbolo a id CoinGecko
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

@app.get("/")
def root():
    return {"mensaje": "API de dólar paralelo Bolivia - /compra | /venta | /dolar-paralelo | /convertir_bob | /precio_cripto"}

@app.get("/compra")
def dolar_compra():
    return obtener_promedio("BUY")

@app.get("/venta")
def dolar_venta():
    return obtener_promedio("SELL")

@app.get("/dolar-paralelo")
def dolar_paralelo():
    compra = obtener_promedio("BUY")
    venta = obtener_promedio("SELL")
    return {
        "fuente": "Binance P2P",
        "timestamp": datetime.now().isoformat(),
        "compra_bs": compra.get("promedio_bs"),
        "venta_bs": venta.get("promedio_bs"),
        "anuncios_compra": compra.get("anuncios_validos"),
        "anuncios_venta": venta.get("anuncios_validos")
    }

@app.get("/convertir_bob")
def convertir_bob(
    monto_bob: float = Query(1000, description="Monto en bolivianos a convertir")
):
    tc_bob_usd = obtener_promedio("BUY").get("promedio_bs")
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

    criptos = {
        "USDT": "Tether (USDT)",
        "BTC": "Bitcoin (BTC)",
        "ETH": "Ethereum (ETH)",
        "USDC": "USD Coin (USDC)",
        "DOGE": "Dogecoin (DOGE)",
        "SOL": "Solana (SOL)",
        "PEPE": "Pepe (PEPE)",
        "TRUMP": "Trump (TRUMP)"
    }
    conversiones_cripto = {}

    for simbolo, nombre in criptos.items():
        id_coingecko = CRYPTO_MAP.get(simbolo)
        if simbolo == "USDT":
            conversiones_cripto[nombre] = round(usd, 2)
        elif id_coingecko:
            precio = obtener_precio_coingecko(id_coingecko)
            if precio:
                valor = usd / precio
                conversiones_cripto[nombre] = round(valor, 6)
            else:
                conversiones_cripto[nombre] = "No disponible"
        else:
            conversiones_cripto[nombre] = "No disponible"

    return {
        "monto_bob": monto_bob,
        "tc_bob_usd": tc_bob_usd,
        "monto_usd": round(usd, 2),
        "conversiones_fiat": conversiones_fiat,
        "conversiones_cripto": conversiones_cripto,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/precio_cripto")
def precio_cripto(
    cripto: str = Query(..., description="Símbolo de la criptomoneda, por ejemplo BTC, ETH")
):
    id_coingecko = CRYPTO_MAP.get(cripto.upper())
    if not id_coingecko:
        return {"error": f"No hay datos para la criptomoneda {cripto}"}
    precio = obtener_precio_coingecko(id_coingecko)
    if precio is None:
        return {"error": f"No se pudo obtener el precio para {cripto}"}
    return {
        "criptomoneda": cripto.upper(),
        "precio_usdt": round(precio, 6),
        "timestamp": datetime.now().isoformat()
    }
