// Sends checks to validator-worker.js, which runs Python in Pyodide. The
// worker starts on first use, so the page itself stays light.

const status = document.getElementById("validator-status");
let worker = null;
let ready = null;
let nextId = 0;
const pending = new Map();

function startWorker() {
  worker = new Worker(new URL("validator-worker.js", import.meta.url), {
    type: "module",
  });
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
    stopWorker(new Error(event.message || "Cannot start the worker"));
  });
}

function stopWorker(err) {
  worker.terminate();
  worker = null;
  ready = null;
  for (const { reject } of pending.values()) {
    reject(err);
  }
  pending.clear();
}

function call(fn, ...args) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, fn, args });
  });
}

function getReady() {
  if (ready === null) {
    status.textContent = "Loading Python (Pyodide)…";
    startWorker();
    ready = call("load").then(
      (info) => {
        status.textContent = `Using ${info}.`;
      },
      (err) => {
        // Discard the failed worker so the next attempt starts fresh.
        if (worker !== null) {
          stopWorker(err);
        }
        status.textContent = `Error: ${err.message}`;
        throw err;
      },
    );
  }
  return ready;
}

function render(output, result) {
  const table = document.createElement("table");
  for (const [key, value] of result.rows) {
    const row = table.insertRow();
    row.insertCell().textContent = key;
    row.insertCell().textContent = value;
  }
  output.className = result.ok ? "validator-ok" : "validator-error";
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
    await getReady();
    render(output, await call(form.dataset.check, ...args));
  } catch (err) {
    output.className = "validator-error";
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
