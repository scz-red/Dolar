const dateElement = document.getElementById("date");
const currencyList = document.getElementById("currencyList");

// Formato de fecha estilo iOS
const now = new Date();
const formatter = new Intl.DateTimeFormat("es-BO", {
  dateStyle: "short",
  timeStyle: "short",
});
dateElement.textContent = formatter.format(now);

let currencies = [];

async function fetchCurrencies() {
  try {
    const response = await fetch("https://scz-red-api.onrender.com/usdt-rate");
    const data = await response.json();

    currencies = data.map(item => ({
      code: item.code,
      name: item.name,
      flag: item.flag || "🌐",
      value: parseFloat(item.rate)
    }));

    renderCurrencies();
  } catch (error) {
    console.error("Error al obtener las monedas:", error);
  }
}

function renderCurrencies() {
  currencyList.innerHTML = "";
  currencies.forEach(({ code, flag, value }) => {
    const item = document.createElement("div");
    item.className = "currency-item";
    item.innerHTML = `
      <div class="currency-flag">
        <span>${flag}</span>
        <span>${code}</span>
      </div>
      <div class="currency-value">${value.toLocaleString()}</div>
    `;
    currencyList.appendChild(item);
  });
}

let currentInput = "";

function inputNumber(num) {
  if (currentInput.length < 15) {
    currentInput += num;
    updateMainValue();
  }
}

function inputOperator(op) {
  if (currentInput && !isNaN(currentInput.slice(-1))) {
    currentInput += op;
  }
}

function clearInput() {
  currentInput = "";
  updateMainValue();
}

function deleteLast() {
  currentInput = currentInput.slice(0, -1);
  updateMainValue();
}

function calculate() {
  try {
    const result = eval(currentInput);
    currentInput = result.toString();
    updateMainValue();
  } catch {
    currentInput = "Error";
    updateMainValue();
  }
}

function updateMainValue() {
  if (!currencies.length) return;
  const value = parseFloat(currentInput) || 0;
  currencies[0].value = value;

  currencies.forEach((c, i) => {
    if (i !== 0) c.value = value * (c.value / currencies[0].value);
  });
  renderCurrencies();
}

fetchCurrencies();
