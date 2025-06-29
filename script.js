const apiUrl = "https://scz-red-api.onrender.com/usdt-rate";

const currencies = [
  { code: "BOB", name: "Boliviano", flag: "🇧🇴" },
  { code: "USD", name: "US Dollar", flag: "🇺🇸" },
  { code: "ETH", name: "Ethereum", flag: "🟣" },
  { code: "BTC", name: "Bitcoin", flag: "🟠" },
  { code: "COP", name: "Colombian Peso", flag: "🇨🇴" },
];

let exchangeRate = 1; // tasa BOB → USD (por ahora)

let inputValue = "";

const dateEl = document.getElementById("date");
const currencyListEl = document.getElementById("currencyList");

// Mostrar fecha/hora actual
function updateDate() {
  const now = new Date();
  dateEl.textContent = now.toLocaleString();
}

// Mostrar monedas y valores
function renderCurrencies() {
  currencyListEl.innerHTML = "";
  currencies.forEach(({ code, name, flag }) => {
    const val = convert(inputValue || 0, code);
    const div = document.createElement("div");
    div.classList.add("currency-item");
    div.innerHTML = `
      <div class="currency-flag"><span>${flag}</span><span>${code}</span></div>
      <div class="currency-value">${val}</div>
    `;
    currencyListEl.appendChild(div);
  });
}

// Convertir BOB a otra moneda usando tasa actual
function convert(amount, currency) {
  if (!amount || isNaN(amount)) return "0";
  const num = Number(amount);
  if (currency === "BOB") return num.toFixed(2);
  if (currency === "USD") return (num / exchangeRate).toFixed(4);
  // Simulaciones para criptos y otras monedas:
  if (currency === "ETH") return (num / 10000).toFixed(6);
  if (currency === "BTC") return (num / 200000).toFixed(8);
  if (currency === "COP") return (num * 7.3).toFixed(2);
  return num.toFixed(2);
}

// Recoger número del teclado
function inputNumber(num) {
  if (num === "." && inputValue.includes(".")) return;
  inputValue += num;
  renderCurrencies();
}

// Borrar input
function clearInput() {
  inputValue = "";
  renderCurrencies();
}

// Borrar último dígito
function deleteLast() {
  inputValue = inputValue.slice(0, -1);
  renderCurrencies();
}

function calculate() {
  // Funcionalidad extra si quieres luego
  // Por ahora solo actualizar conversion
  renderCurrencies();
}

// Traer tipo de cambio real de API
async function fetchExchangeRate() {
  try {
    const res = await fetch(apiUrl);
    const data = await res.json();
    exchangeRate = parseFloat(data.averageRate) || 6.9;
    renderCurrencies();
  } catch {
    exchangeRate = 6.9; // fallback
    renderCurrencies();
  }
}

// Init
function init() {
  updateDate();
  fetchExchangeRate();
  setInterval(updateDate, 1000);
  setInterval(fetchExchangeRate, 60 * 1000);
}

init();
