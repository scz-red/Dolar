from fastapi import FastAPI, Query
import requests
from datetime import datetime

app = FastAPI()

HEADERS = {
    "Content-Type": "application/json"
}

# Cache global para IDs de criptos (símbolo -> id)
CACHE_COINS = {}

def cargar_cache_coins():
    global CACHE_COINS
    try:
        url = "https://api.coingecko.com/api/v3/coins/list"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        coins = r.json()
        CACHE_COINS = {coin['symbol'].lower(): coin['id'] for coin in coins}
        print(f"Cargados {len(CACHE_COINS)} símbolos de cripto en cache")
    except Exception as e:
        print(f"Error cargando cache de monedas: {e}")

# Carga al iniciar la app
cargar_cache_coins()

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

def obtener_precio_coingecko(cripto_simbolo):
    cripto_id = CACHE_COINS.get(cripto_simbolo.lower())
    if not cripto_id:
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cripto_id}&vs_currencies=usd"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get(cripto_id, {}).get('usd')
    except Exception as e:
        print(f"Error obtener_precio_coingecko: {e}")
        return None

@app.get("/")
def root():
    return {"mensaje": "API dólar paralelo Bolivia - /compra | /venta | /dolar-paralelo | /convertir_bob | /precio_cripto"}

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
        "DAI": "Dai (DAI)"
    }
    conversiones_cripto = {}

    for cripto, nombre in criptos.items():
        if cripto == "USDT":
            conversiones_cripto[nombre] = round(usd, 2)
        else:
            precio = obtener_precio_coingecko(cripto)
            if precio:
                valor = usd / precio
                conversiones_cripto[nombre] = round(valor, 6)
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
    precio = obtener_precio_coingecko(cripto)
    if precio is None:
        return {"error": f"No se pudo obtener el precio para {cripto}"}
    return {
        "criptomoneda": cripto.upper(),
        "precio_usdt": round(precio, 6),
        "timestamp": datetime.now().isoformat()
    }
