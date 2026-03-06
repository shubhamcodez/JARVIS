const displayEl = document.getElementById("display");

let currentValue = "0";
let previousValue = null;
let operation = null;
let shouldResetDisplay = false;

function updateDisplay() {
  const text = currentValue.length > 12 ? Number(currentValue).toExponential(6) : currentValue;
  displayEl.textContent = text;
}

function inputDigit(num) {
  if (shouldResetDisplay) {
    currentValue = num;
    shouldResetDisplay = false;
  } else {
    if (currentValue === "0" && num !== ".") currentValue = num;
    else currentValue += num;
  }
  updateDisplay();
}

function inputDecimal() {
  if (shouldResetDisplay) {
    currentValue = "0.";
    shouldResetDisplay = false;
  } else if (!currentValue.includes(".")) {
    currentValue += ".";
  }
  updateDisplay();
}

function setOperation(op) {
  const num = parseFloat(currentValue);
  if (previousValue !== null && operation !== null && !shouldResetDisplay) {
    equals();
    previousValue = parseFloat(currentValue);
  } else {
    previousValue = num;
  }
  operation = op;
  shouldResetDisplay = true;
  updateDisplay();
}

async function equals() {
  if (previousValue === null || operation === null) return;
  const a = previousValue;
  const b = parseFloat(currentValue);
  const invoke = window.__TAURI__.core.invoke;
  try {
    const result = await invoke("calculate", { a, b, op: operation });
    currentValue = String(Number.isInteger(result) ? result : parseFloat(Number(result).toPrecision(12)));
  } catch (err) {
    currentValue = "Error";
  }
  previousValue = null;
  operation = null;
  shouldResetDisplay = true;
  updateDisplay();
}

function clearAll() {
  currentValue = "0";
  previousValue = null;
  operation = null;
  shouldResetDisplay = false;
  updateDisplay();
}

function backspace() {
  if (shouldResetDisplay) return;
  if (currentValue.length <= 1) {
    currentValue = "0";
  } else {
    currentValue = currentValue.slice(0, -1);
  }
  updateDisplay();
}

document.querySelectorAll(".btn-num[data-num]").forEach((btn) => {
  btn.addEventListener("click", () => inputDigit(btn.dataset.num));
});

document.querySelector("[data-action='decimal']").addEventListener("click", inputDecimal);

document.querySelectorAll(".btn-op[data-op]").forEach((btn) => {
  btn.addEventListener("click", () => setOperation(btn.dataset.op));
});

document.querySelector("[data-action='equals']").addEventListener("click", equals);
document.querySelector("[data-action='clear']").addEventListener("click", clearAll);
document.querySelector("[data-action='back']").addEventListener("click", backspace);

document.addEventListener("keydown", (e) => {
  if (e.key >= "0" && e.key <= "9") inputDigit(e.key);
  else if (e.key === ".") inputDecimal();
  else if (e.key === "+" || e.key === "-" || e.key === "*" || e.key === "/" || e.key === "%") setOperation(e.key);
  else if (e.key === "Enter" || e.key === "=") { e.preventDefault(); equals(); }
  else if (e.key === "Escape" || e.key === "c" || e.key === "C") clearAll();
  else if (e.key === "Backspace") { e.preventDefault(); backspace(); }
});

updateDisplay();
