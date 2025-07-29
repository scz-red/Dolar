<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Calculadora al Paralelo</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #4356f9;
      --primary-dark: #23389c;
      --background: #f8fafc;
      --white: #fff;
      --gray: #ececec;
      --border: #e0e0e0;
      --shadow: 0 4px 20px rgba(67,86,249,0.08);
      --radius: 24px;
    }
    html, body {
      margin: 0; padding: 0; box-sizing: border-box;
      background: var(--background);
      font-family: 'Inter', Arial, sans-serif;
    }
    .main-box {
      max-width: 420px;
      margin: 48px auto 32px auto;
      background: var(--white);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .hero {
      background: linear-gradient(135deg, var(--primary), #6c81ff 95%);
      color: #fff;
      padding: 38px 30px 18px 30px;
    }
    .hero-title {
      font-size: 2.1rem; font-weight: 700; line-height: 1.1;
      margin-bottom: 9px;
      letter-spacing: -1.2px;
    }
    .hero-desc {
      font-size: 1.02rem; font-weight: 400; opacity: 0.93;
    }
    .calc {
      background: var(--white);
      border-radius: 0 0 var(--radius) var(--radius);
      padding: 30px 24px 16px 24px;
      box-shadow: var(--shadow);
    }
    .input-row {
      display: flex;
      gap: 12px;
      margin-bottom: 20px;
    }
    .input-row input {
      flex: 1 1 0; font-size: 1.5rem;
      border: 1.5px solid var(--border);
      border-radius: 12px;
      padding: 10px 16px;
      outline: none;
      transition: border 0.2s;
    }
    .input-row input:focus { border: 1.5px solid var(--primary); }
    .input-row button {
      background: var(--primary);
      color: #fff;
      border: none;
      font-weight: 600;
      padding: 0 18px;
      font-size: 1.1rem;
      border-radius: 12px;
      cursor: pointer;
      transition: background 0.16s;
    }
    .input-row button:active { background: var(--primary-dark); }
    .res-row {
      display: flex;
      gap: 18px;
      margin-bottom: 12px;
      justify-content: center;
    }
    .res-card {
      background: var(--gray);
      padding: 16px 20px;
      border-radius: 18px;
      flex: 1 1 0;
      text-align: center;
      box-shadow: 0 1px 6px rgba(67,86,249,0.04);
    }
    .res-label {
      font-size: 1rem;
      font-weight: 500;
      color: #485;
      letter-spacing: .04em;
      opacity: .92;
      margin-bottom: 2px;
    }
    .res-value {
      font-size: 1.5rem; font-weight: 700; color: var(--primary);
      letter-spacing: .02em;
    }
    .section {
      margin: 16px 0 0 0;
      padding: 0 22px 0 22px;
    }
    .section-title {
      font-weight: 700; font-size: 1.13rem; color: var(--primary);
      margin-bottom: 6px;
      display: flex; align-items: center; gap: 7px;
    }
    .list {
      background: var(--white);
      border-radius: 18px;
      box-shadow: 0 2px 10px rgba(70,80,220,0.06);
      margin-bottom: 18px;
    }
    .item {
      display: flex; align-items: center;
      border-bottom: 1px solid var(--gray);
      padding: 12px 9px;
      font-size: 1.09rem;
    }
    .item:last-child { border-bottom: none; }
    .item .icon {
      width: 38px; height: 38px;
      border-radius: 8px;
      margin-right: 17px;
      object-fit: contain;
      background: #f4f7fc;
      border: 1.5px solid #dde4f0;
    }
    .item-details {
      flex: 1 1 0;
      min-width: 0;
    }
    .item-label {
      font-weight: 600;
      font-size: 1.06rem;
      color: #191929;
    }
    .item-code {
      font-size: .94rem; color: #888;
    }
    .item-value {
      font-weight: 700; color: var(--primary-dark);
      font-size: 1.08rem;
      text-align: right;
      min-width: 84px;
    }
    @media (max-width: 600px) {
      .main-box { max-width: 99vw; margin: 18px 0; }
      .hero { padding: 25px 10px 13px 10px; }
      .calc { padding: 19px 7px 12px 7px; }
      .section { padding: 0 6px; }
    }
  </style>
</head>
<body>
  <div class="main-box">
    <div class="hero">
      <div class="hero-title">Calculadora al Paralelo</div>
      <div class="hero-desc">Convierte BOB a diferentes monedas al instante</div>
    </div>
    <div class="calc">
      <div class="input-row">
        <input type="number" id="montoInput" placeholder="Monto en BOB" value="1000" min="0" step="any" autocomplete="off" />
      </div>
      <div class="res-row">
        <div class="res-card">
          <div class="res-label">USD/BOB</div>
          <div class="res-value" id="usdBob">-</div>
        </div>
        <div class="res-card">
          <div class="res-label">EUR/BOB</div>
          <div class="res-value" id="eurBob">-</div>
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title"><img src="https://img.icons8.com/color/36/money.png" width="26" style="margin-right:6px;vertical-align:-6px">Monedas tradicionales</div>
      <div class="list" id="fiatList"></div>
      <div class="section-title" style="margin-top:16px;"><img src="https://img.icons8.com/color/36/blockchain-new.png" width="26" style="margin-right:6px;vertical-align:-6px">Criptomonedas</div>
      <div class="list" id="cryptoList"></div>
    </div>
  </div>
  <script>
const fiatCurrencies = {
  "Dólar estadounidense": { code: "USD", icon: "https://currencyfreaks.com/photos/flags/usd.png" },
  "Euro": { code: "EUR", icon: "https://currencyfreaks.com/photos/flags/eur.png" },
  "Peso colombiano": { code: "COP", icon: "https://currencyfreaks.com/photos/flags/cop.png" },
  "Peso argentino": { code: "ARS", icon: "https://currencyfreaks.com/photos/flags/ars.png" },
  "Peso chileno": { code: "CLP", icon: "https://currencyfreaks.com/photos/flags/clp.png" },
  "Real brasileño": { code: "BRL", icon: "https://currencyfreaks.com/photos/flags/brl.png" },
  "Sol peruano": { code: "PEN", icon: "https://currencyfreaks.com/photos/flags/pen.png" },
  "Yuan chino": { code: "CNY", icon: "https://currencyfreaks.com/photos/flags/cny.png" },
  "Guaraní paraguayo": { code: "PYG", icon: "https://currencyfreaks.com/photos/flags/pyg.png" },
  "Peso mexicano": { code: "MXN", icon: "https://currencyfreaks.com/photos/flags/mxn.png" }
};
const cryptoCurrencies = [
  { name: "Tether (USDT)", code: "USDT", icon: "paralelo/1.png" },
  { name: "Bitcoin", code: "BTC", icon: "paralelo/2.png" },
  { name: "Ethereum", code: "ETH", icon: "paralelo/3.png" },
  { name: "USD Coin", code: "USDC", icon: "paralelo/4.png" },
  { name: "Dogecoin", code: "DOGE", icon: "paralelo/5.png" },
  { name: "Solana", code: "SOL", icon: "paralelo/6.png" },
  { name: "Pepe", code: "PEPE", icon: "paralelo/7.png" },
  { name: "Trump", code: "TRUMP", icon: "paralelo/8.png" }
];
const montoInput = document.getElementById('montoInput');
const fiatList = document.getElementById('fiatList');
const cryptoList = document.getElementById('cryptoList');
const usdBob = document.getElementById('usdBob');
const eurBob = document.getElementById('eurBob');
const API_URL = 'https://api.lupo.lat/convertir_bob?monto_bob=';
const CACHE_MINUTES = 2;

function setCache(monto, data) {
  localStorage.setItem('calcCache_' + monto, JSON.stringify({
    data, timestamp: Date.now()
  }));
}
function getCache(monto) {
  const val = localStorage.getItem('calcCache_' + monto);
  if (!val) return null;
  try {
    const obj = JSON.parse(val);
    if (Date.now() - obj.timestamp < CACHE_MINUTES * 60 * 1000) return obj.data;
  } catch (e) {}
  return null;
}

function formatNumber(n) {
  if (n === null || n === undefined) return '-';
  if (typeof n === 'number') n = n.toFixed(2);
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.').replace('.', ',');
}

async function calcular() {
  let monto = +montoInput.value;
  if (!monto || monto < 0) monto = 0;
  let data = getCache(monto);
  if (!data) {
    try {
      const resp = await fetch(API_URL + monto);
      data = await resp.json();
      setCache(monto, data);
    } catch {
      fiatList.innerHTML = '<div style="padding:18px;">Error de red/API</div>';
      cryptoList.innerHTML = '';
      usdBob.textContent = eurBob.textContent = '-';
      return;
    }
  }
  // Mostrar USD/BOB, EUR/BOB
  usdBob.textContent = data.conversiones_fiat && data.conversiones_fiat["Dólar estadounidense"]
    ? formatNumber(data.conversiones_fiat["Dólar estadounidense"]) : '-';
  eurBob.textContent = data.conversiones_fiat && data.conversiones_fiat["Euro"]
    ? formatNumber(data.conversiones_fiat["Euro"]) : '-';
  // Listar monedas tradicionales
  fiatList.innerHTML = '';
  if (data.conversiones_fiat) {
    Object.entries(fiatCurrencies).forEach(([name, val]) => {
      let amount = data.conversiones_fiat[name];
      fiatList.innerHTML += `<div class="item"><img class="icon" src="${val.icon}" alt="${val.code}"><div class="item-details"><div class="item-label">${name}</div><div class="item-code">${val.code}</div></div><div class="item-value">${formatNumber(amount)}</div></div>`;
    });
  }
  // Listar cripto
  cryptoList.innerHTML = '';
  if (data.conversiones_cripto) {
    cryptoCurrencies.forEach(obj => {
      let val = data.conversiones_cripto[obj.name] || data.conversiones_cripto[obj.code] || 0;
      cryptoList.innerHTML += `<div class="item"><img class="icon" src="${obj.icon}" alt="${obj.code}"><div class="item-details"><div class="item-label">${obj.name}</div><div class="item-code">${obj.code}</div></div><div class="item-value">${formatNumber(val)}</div></div>`;
    });
  }
}

montoInput.addEventListener('input', () => calcular());
window.addEventListener('DOMContentLoaded', () => calcular());
  </script>
</body>
</html>
