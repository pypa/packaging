// Runs the packaging source from this docs build in Pyodide. Python is
// loaded on first use, so the page itself stays light.

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";

const status = document.getElementById("validator-status");
let helpers = null;

async function fetchOk(name) {
  const response = await fetch(new URL(name, import.meta.url));
  if (!response.ok) {
    throw new Error(`Cannot fetch ${name}: ${response.status}`);
  }
  return response;
}

async function load() {
  status.textContent = "Loading Python (Pyodide)…";
  const [pyodide, zip, source] = await Promise.all([
    import(PYODIDE_URL + "pyodide.mjs").then((m) =>
      m.loadPyodide({ indexURL: PYODIDE_URL }),
    ),
    fetchOk("packaging.zip").then((r) => r.arrayBuffer()),
    fetchOk("validator.py").then((r) => r.text()),
  ]);
  pyodide.unpackArchive(zip, "zip", { extractDir: "/packaging-src" });
  pyodide.runPython("import sys; sys.path.insert(0, '/packaging-src')");
  const namespace = pyodide.toPy({});
  pyodide.runPython(source, { globals: namespace });
  status.textContent = `Using ${namespace.get("INFO")}.`;
  return namespace;
}

function getHelpers() {
  if (helpers === null) {
    helpers = load().catch((err) => {
      helpers = null;
      status.textContent = `Error: ${err.message}`;
      throw err;
    });
  }
  return helpers;
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
    const namespace = await getHelpers();
    const fn = namespace.get(form.dataset.check);
    try {
      render(output, JSON.parse(fn(...args)));
    } finally {
      fn.destroy();
    }
  } catch (err) {
    output.className = "validator-error";
    output.textContent = String(err.message ?? err);
  }
}

for (const form of document.querySelectorAll("form.validator")) {
  form.addEventListener("submit", check);
  // Start the download as soon as the reader shows interest.
  form.addEventListener("focusin", () => getHelpers().catch(() => {}), {
    once: true,
  });
}
