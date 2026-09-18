/**
 * renderer.js
 * Logica de UI: configuracion (persistida en LocalStorage), carga del
 * catalogo en XML via el proceso principal, y paginacion client-side.
 */
const STORAGE_KEY = "libreria.catalogConfig.v1";

const DEFAULTS = {
  baseUrl: "http://34.51.96.249:5001",
  endpoint: "/books",
  pageSize: 12,
};

const state = {
  books: [],
  page: 1,
  pageSize: DEFAULTS.pageSize,
};

const els = {
  toggleConfig: document.getElementById("toggleConfig"),
  configPanel: document.getElementById("configPanel"),
  configForm: document.getElementById("configForm"),
  baseUrl: document.getElementById("baseUrl"),
  endpoint: document.getElementById("endpoint"),
  pageSize: document.getElementById("pageSize"),
  resetConfig: document.getElementById("resetConfig"),
  statusText: document.getElementById("statusText"),
  reloadBtn: document.getElementById("reloadBtn"),
  catalog: document.getElementById("catalog"),
  prevPage: document.getElementById("prevPage"),
  nextPage: document.getElementById("nextPage"),
  pageIndicator: document.getElementById("pageIndicator"),
};

function loadConfig() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw);
    return {
      baseUrl: parsed.baseUrl || DEFAULTS.baseUrl,
      endpoint: parsed.endpoint || DEFAULTS.endpoint,
      pageSize: Number(parsed.pageSize) || DEFAULTS.pageSize,
    };
  } catch (err) {
    console.warn("No se pudo leer la configuracion guardada:", err);
    return { ...DEFAULTS };
  }
}

function saveConfig(config) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

function buildCatalogUrl(config) {
  const base = config.baseUrl.trim().replace(/\/+$/, "");
  const path = config.endpoint.trim().startsWith("/")
    ? config.endpoint.trim()
    : `/${config.endpoint.trim()}`;
  const url = new URL(`${base}${path}`);
  // La app consume EXCLUSIVAMENTE XML: se fuerza el formato aunque el
  // servidor ya lo devuelva por defecto.
  url.searchParams.set("format", "xml");
  return url.toString();
}

function setStatus(message, isError = false) {
  els.statusText.textContent = message;
  els.statusText.parentElement.classList.toggle("error", isError);
}

function parseBooksXml(xmlText) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlText, "application/xml");

  const parseError = doc.querySelector("parsererror");
  if (parseError) {
    throw new Error("La respuesta del servidor no es un XML valido.");
  }

  const bookNodes = Array.from(doc.getElementsByTagName("book"));
  return bookNodes.map((node) => {
    const text = (tag) => node.getElementsByTagName(tag)[0]?.textContent?.trim() || "";
    return {
      isbn: node.getAttribute("isbn") || "",
      title: text("title"),
      year: text("year"),
      price: text("price"),
      stock: text("stock"),
      format: text("format"),
      author: text("author") || "Autor desconocido",
      genre: text("genre") || "Sin genero",
      imageUrl: text("image_url"),
    };
  });
}

function formatPrice(price) {
  const value = Number(price);
  if (Number.isNaN(value)) return price;
  return value.toLocaleString("es-MX", { style: "currency", currency: "MXN" });
}

function renderPage() {
  const totalPages = Math.max(1, Math.ceil(state.books.length / state.pageSize));
  state.page = Math.min(Math.max(1, state.page), totalPages);

  const start = (state.page - 1) * state.pageSize;
  const pageBooks = state.books.slice(start, start + state.pageSize);

  els.catalog.innerHTML = "";

  if (pageBooks.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No hay libros para mostrar.";
    els.catalog.appendChild(empty);
  }

  for (const book of pageBooks) {
    els.catalog.appendChild(buildCard(book));
  }

  els.pageIndicator.textContent = `Pagina ${state.page} de ${totalPages}`;
  els.prevPage.disabled = state.page <= 1;
  els.nextPage.disabled = state.page >= totalPages;
}

function buildCard(book) {
  const card = document.createElement("article");
  card.className = "card";

  const img = document.createElement("img");
  img.className = "card-image";
  img.loading = "lazy";
  img.alt = `Portada de ${book.title || book.isbn}`;
  img.src = book.imageUrl || "";
  img.onerror = () => {
    img.onerror = null;
    img.src =
      "data:image/svg+xml;utf8," +
      encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600"><rect width="100%" height="100%" fill="#e4e4ea"/><text x="50%" y="50%" font-family="sans-serif" font-size="18" fill="#8a8a94" text-anchor="middle">Sin imagen</text></svg>'
      );
  };

  const body = document.createElement("div");
  body.className = "card-body";

  const title = document.createElement("h2");
  title.className = "card-title";
  title.textContent = book.title || "(Sin titulo)";

  body.appendChild(title);
  body.appendChild(row("Autor(es)", book.author));
  body.appendChild(row("ISBN", book.isbn));
  body.appendChild(row("Stock", book.stock));
  body.appendChild(row("Ano", book.year));
  body.appendChild(row("Genero", book.genre));

  const price = document.createElement("div");
  price.className = "card-price";
  price.textContent = formatPrice(book.price);
  body.appendChild(price);

  card.appendChild(img);
  card.appendChild(body);
  return card;
}

function row(label, value) {
  const el = document.createElement("div");
  el.className = "card-row";
  el.innerHTML = `<span>${label}</span><strong></strong>`;
  el.querySelector("strong").textContent = value || "-";
  return el;
}

async function loadCatalog(config) {
  setStatus("Cargando catalogo...");
  els.reloadBtn.disabled = true;

  const url = buildCatalogUrl(config);
  const result = await window.catalogAPI.fetchXml(url);

  els.reloadBtn.disabled = false;

  if (!result.ok) {
    setStatus(`Error al cargar el catalogo: ${result.error}`, true);
    state.books = [];
    renderPage();
    return;
  }

  try {
    state.books = parseBooksXml(result.data);
    state.page = 1;
    setStatus(`${state.books.length} libro(s) cargados desde ${url}`);
    renderPage();
  } catch (err) {
    setStatus(`Error al procesar el XML: ${err.message}`, true);
    state.books = [];
    renderPage();
  }
}

function applyConfigToForm(config) {
  els.baseUrl.value = config.baseUrl;
  els.endpoint.value = config.endpoint;
  els.pageSize.value = String(config.pageSize);
}

function init() {
  const config = loadConfig();
  state.pageSize = config.pageSize;
  applyConfigToForm(config);

  els.toggleConfig.addEventListener("click", () => {
    els.configPanel.hidden = !els.configPanel.hidden;
  });

  els.configForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const newConfig = {
      baseUrl: els.baseUrl.value.trim() || DEFAULTS.baseUrl,
      endpoint: els.endpoint.value.trim() || DEFAULTS.endpoint,
      pageSize: Number(els.pageSize.value) || DEFAULTS.pageSize,
    };
    saveConfig(newConfig);
    state.pageSize = newConfig.pageSize;
    loadCatalog(newConfig);
  });

  els.resetConfig.addEventListener("click", () => {
    saveConfig(DEFAULTS);
    state.pageSize = DEFAULTS.pageSize;
    applyConfigToForm(DEFAULTS);
    loadCatalog(DEFAULTS);
  });

  els.reloadBtn.addEventListener("click", () => loadCatalog(loadConfig()));

  els.prevPage.addEventListener("click", () => {
    state.page -= 1;
    renderPage();
  });

  els.nextPage.addEventListener("click", () => {
    state.page += 1;
    renderPage();
  });

  loadCatalog(config);
}

init();
