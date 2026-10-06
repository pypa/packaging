// Sends checks to validator-worker.js, which runs Python in Pyodide. The
// worker starts on first use, so the page itself stays light.

const status = document.getElementById("validator-status");
let ready = null;

function setStatus(state, text) {
  status.dataset.state = state;
  status.textContent = text;
}

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
  setStatus("ready", `Using ${rows.Info}`);
  return call;
}

function getReady() {
  if (ready === null) {
    setStatus("loading", "Loading Python (Pyodide)…");
    ready = start().catch((err) => {
      // Discard the failed worker so the next attempt starts fresh.
      ready = null;
      setStatus("error", `Error: ${err.message}`);
      throw err;
    });
  }
  return ready;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function render(output, result) {
  const { Normalized, Error: error, ...rows } = result.rows;
  output.className = result.ok ? "valid" : "invalid";
  const title = result.ok ? "✓ Valid" : "✗ Invalid";
  const parts = [el("div", "validator-result-title", title)];
  if (Normalized !== undefined) {
    parts.push(el("div", "validator-normalized", Normalized));
  }
  if (Object.keys(rows).length) {
    const dl = el("dl");
    for (const [key, value] of Object.entries(rows)) {
      const dd = el("dd", "", value);
      dd.dataset.value = value;
      dl.append(el("dt", "", key), dd);
    }
    parts.push(dl);
  }
  if (error !== undefined) {
    parts.push(el("pre", "", error));
  }
  output.replaceChildren(...parts);
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
  output.className = "";
  output.replaceChildren(el("div", "validator-result-title", "Working…"));
  try {
    const call = await getReady();
    render(output, await call(form.dataset.check, ...args));
  } catch (err) {
    output.className = "invalid";
    output.replaceChildren(
      el("div", "validator-result-title", "✗ Error"),
      el("pre", "", err.message),
    );
  }
}

// Adds buttons that fill in and check example inputs.
function addExamples(form) {
  const examples = JSON.parse(form.dataset.examples ?? "[]");
  const invalid = JSON.parse(form.dataset.invalidExamples ?? "[]");
  if (!examples.length && !invalid.length) {
    return;
  }
  const inputs = form.querySelectorAll("input");
  const row = el("div", "validator-examples", "Try:");
  for (const example of [...examples, ...invalid]) {
    const values = [example].flat();
    const label = values[1] ? `${values[1]} in ${values[0]}` : values[0];
    const className = invalid.includes(example) ? "invalid" : "";
    const button = el("button", className, label);
    button.type = "button";
    button.addEventListener("click", () => {
      inputs.forEach((input, i) => (input.value = values[i] ?? ""));
      form.requestSubmit();
    });
    row.append(button);
  }
  form.querySelector("output").before(row);
}

for (const form of document.querySelectorAll("form.validator")) {
  addExamples(form);
  form.addEventListener("submit", check);
  // Start the download as soon as the reader shows interest.
  form.addEventListener("focusin", () => getReady().catch(() => {}), {
    once: true,
  });
}
