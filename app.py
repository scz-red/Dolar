from flask import Flask, jsonify
import requests

app = Flask(__name__)

def obtener_dolar_paralelo():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    payload = {
        "asset": "USDT",
        "fiat": "BOB",
        "merchantCheck": False,
        "page": 1,
        "payTypes": [],
        "publisherType": None,
        "rows": 10,
        "tradeType": "SELL"
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    data = response.json()

    precios = [float(oferta["adv"]["price"]) for oferta in data["data"]]
    promedio = sum(precios) / len(precios)

    return round(promedio, 2)

@app.route("/")
def home():
    return "API del dólar paralelo en Bolivia 🇧🇴"

@app.route("/dolar-paralelo")
def dolar_paralelo():
    promedio = obtener_dolar_paralelo()
    return jsonify({
        "moneda": "USD",
        "fiat": "BOB",
        "tipo": "venta",
        "promedio_10_ofertas": promedio,
        "fuente": "Binance P2P"
    })

if __name__ == "__main__":
    app.run(debug=True)
