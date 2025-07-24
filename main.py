# ... resto del código igual ...

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

    response = requests.post(url, headers=HEADERS, json=data)
    anuncios = response.json().get("data", [])

    precios_validos = []

    for anuncio in anuncios:
        adv = anuncio.get("adv", {})
        advertiser = anuncio.get("advertiser", {})

        precio = float(adv.get("price", 0))
        min_limit = float(adv.get("minSingleTransAmount", 0))
        conditions = adv.get("tradeMethods", [])

        # 🚫 Filtrar anuncios con restricciones como "mínimo 1 BTC" o parecidas
        restricciones = any(
            (
                (method.get("tradeMethodName") and "BTC" in method.get("tradeMethodName").upper())
                or
                (method.get("identifier") and "BTC" in method.get("identifier").upper())
            )
            for method in conditions
        )

        if restricciones:
            continue

        precios_validos.append(precio)

        if len(precios_validos) == 5:
            break

    if not precios_validos:
        return {"error": "No hay suficientes anuncios válidos."}

    promedio = sum(precios_validos) / len(precios_validos)
    return {
        "direccion": direccion.lower(),
        "promedio_bs": round(promedio, 2),
        "anuncios_validos": len(precios_validos),
        "timestamp": datetime.now().isoformat()
    }

# ... resto del código igual ...
