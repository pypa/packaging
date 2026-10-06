// Sends checks to validator-worker.js, which runs Python in Pyodide. The
// worker starts on first use, so the page itself stays light.

const status = document.getElementById("validator-status");
let ready = null;

// Starts a worker and resolves to a function that sends it one check.
async function start() {
  const worker = new Worker(new URL("validator-worker.js", import.meta.url), {
    type: "module",
  });
  const pending = new Map();
  let nextId = 0;
  worker.addEventListener("message", ({ data: { id, result, error } }) => {
    const { resolve, reject } = pending.get(id);
    pending.delete(id);
    if (error === undefined) {
      resolve(result);
    } else {
      reject(new Error(error));
    }
  });
  worker.addEventListener("error", (event) => {
    event.preventDefault();
    worker.terminate();
    for (const { reject } of pending.values()) {
      reject(new Error(event.message || "Cannot start the worker"));
    }
    pending.clear();
  });
  const call = (...args) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      worker.postMessage({ id, args });
    });
  const { rows } = await call("info");
  status.textContent = `Using ${rows.Info}.`;
  return call;
}

function getReady() {
  if (ready === null) {
    status.textContent = "Loading Python (Pyodide)…";
    ready = start().catch((err) => {
      // Discard the failed worker so the next attempt starts fresh.
      ready = null;
      status.textContent = `Error: ${err.message}`;
      throw err;
    });
  }
  return ready;
}

function render(output, result) {
  const table = document.createElement("table");
  for (const [key, value] of Object.entries(result.rows)) {
    const row = table.insertRow();
    row.insertCell().textContent = key;
    row.insertCell().textContent = value;
  }
  output.className = result.ok ? "admonition tip" : "admonition danger";
  output.replaceChildren(table);
}

async function check(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const output = form.querySelector("output");
  const args = [...form.querySelectorAll("input")].map((i) => i.value.trim());
  if (!args[0]) {
    output.replaceChildren();
    return;
  }
  output.textContent = "Working…";
  try {
    const call = await getReady();
    render(output, await call(form.dataset.check, ...args));
  } catch (err) {
    output.className = "admonition danger";
    output.textContent = err.message;
  }
}

for (const form of document.querySelectorAll("form.validator")) {
  form.addEventListener("submit", check);
  // Start the download as soon as the reader shows interest.
  form.addEventListener("focusin", () => getReady().catch(() => {}), {
    once: true,
  });
}
