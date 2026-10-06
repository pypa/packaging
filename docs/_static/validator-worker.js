// Runs the packaging source from this docs build in Pyodide, off the main
// thread. Each request is {id, args}; each reply is {id, result} or
// {id, error}. The args go to ``run`` in validator.py.

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";

async function fetchOk(name) {
  const response = await fetch(new URL(name, import.meta.url));
  if (!response.ok) {
    throw new Error(`Cannot fetch ${name}: ${response.status}`);
  }
  return response;
}

async function load() {
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
  return namespace.get("run");
}

const run = load();

self.addEventListener("message", async ({ data: { id, args } }) => {
  try {
    self.postMessage({ id, result: JSON.parse((await run)(...args)) });
  } catch (err) {
    self.postMessage({ id, error: String(err.message ?? err) });
  }
});
