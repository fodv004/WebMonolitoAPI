/*
 * Mapa de rastreo. Java llama a estas funciones con WebEngine.executeScript:
 *   showEnvio(envio)                                  snapshot / GET /envios/<codigo>
 *   updatePosition(lat, lon, progreso, estado)        cada update del WebSocket
 *   resetMap()                                        limpia y centra en Monterrey
 *   refrescarTamano()                                 recalcula el tamaño tras un cambio del WebView
 * El JSON del envio viene en snake_case (ruta.puntos, posicion.latitude, progreso...).
 */
window.onerror = function (msg, src, line) { alert('Error JS: ' + msg + ' (linea ' + line + ')'); };

var MONTERREY = [25.6866, -100.3161];
var map = L.map('map', {
  zoomControl: true,
  /* Sin animaciones de zoom/fade: en el WebView dejaban tiles de dos zooms mezclados o sin pintar. */
  zoomAnimation: false,
  fadeAnimation: false,
  markerZoomAnimation: false
}).setView(MONTERREY, 12);
var tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  keepBuffer: 4,
  attribution: '&copy; colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);
/* Avisa a Java (log) si OSM rechaza tiles; maximo 3 avisos para no llenar la consola. */
var tileErrors = 0;
tiles.on('tileerror', function (e) {
  tileErrors++;
  if (tileErrors <= 3) alert('Tile no disponible: ' + (e.tile && e.tile.src));
});

var TRUCK_SVG =
  '<svg width="26" height="26" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">' +
  '<rect x="4" y="16" width="34" height="26" rx="3" fill="#2563eb"/>' +
  '<path d="M38 24h12l8 10v8H38z" fill="#1e40af"/>' +
  '<rect x="42" y="27" width="8" height="7" rx="1" fill="#dbeafe"/>' +
  '<circle cx="16" cy="45" r="6" fill="#111827"/><circle cx="16" cy="45" r="2.5" fill="#e5e7eb"/>' +
  '<circle cx="48" cy="45" r="6" fill="#111827"/><circle cx="48" cy="45" r="2.5" fill="#e5e7eb"/>' +
  '<rect x="9" y="22" width="20" height="3" rx="1.5" fill="#bfdbfe"/>' +
  '</svg>';

function truckIcon(delivered) {
  return L.divIcon({
    className: 'truck-icon' + (delivered ? ' delivered' : ''),
    html: '<div class="bubble">' + TRUCK_SVG + '</div>',
    iconSize: [42, 42], iconAnchor: [21, 21]
  });
}

var flagIcon = L.divIcon({
  className: 'flag-icon',
  html: '<svg width="28" height="30" viewBox="0 0 28 30" xmlns="http://www.w3.org/2000/svg">' +
        '<rect x="3" y="2" width="2.5" height="27" rx="1" fill="#0f172a"/>' +
        '<path d="M5.5 3h19l-4 6 4 6h-19z" fill="#16a34a" stroke="#0f172a" stroke-width="1"/></svg>',
  iconSize: [28, 30], iconAnchor: [4, 29]
});

/* true cuando el usuario movio o hizo zoom: al redimensionar ya no se reencuadra la ruta. */
var userMoved = false;
map.on('dragstart', function () { userMoved = true; });
map.on('zoomstart', function (e) { if (!programmatic) userMoved = true; });
var programmatic = false;

var routeLine = null, doneLine = null, truck = null, startMk = null, endMk = null;
var routePts = [], cum = [];
var lastPos = null;

function hav(a, b) {
  var R = 6371000, toR = Math.PI / 180;
  var dLat = (b[0] - a[0]) * toR, dLon = (b[1] - a[1]) * toR;
  var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
          Math.cos(a[0] * toR) * Math.cos(b[0] * toR) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, h)));
}

/* Puntos de la ruta desde el inicio hasta la fraccion p (0..1) de su longitud. */
function routePrefix(p) {
  if (routePts.length < 2) return [];
  var total = cum[cum.length - 1];
  var target = Math.max(0, Math.min(1, p)) * total;
  var out = [routePts[0]];
  for (var i = 1; i < routePts.length; i++) {
    if (cum[i] <= target) { out.push(routePts[i]); continue; }
    var seg = cum[i] - cum[i - 1];
    var f = seg > 0 ? (target - cum[i - 1]) / seg : 0;
    out.push([routePts[i - 1][0] + (routePts[i][0] - routePts[i - 1][0]) * f,
              routePts[i - 1][1] + (routePts[i][1] - routePts[i - 1][1]) * f]);
    break;
  }
  return out;
}

function clearLayers() {
  [routeLine, doneLine, truck, startMk, endMk].forEach(function (l) { if (l) map.removeLayer(l); });
  routeLine = doneLine = truck = startMk = endMk = null;
  routePts = []; cum = []; lastPos = null;
}

function resetMap() {
  clearLayers();
  userMoved = false;
  programmatic = true;
  map.setView(MONTERREY, 12, { animate: false });
  programmatic = false;
}

function setDone(progreso, pos, estado) {
  if (!doneLine) return;
  var pts;
  if (estado === 'ENTREGADO') {
    pts = routePts.slice();
  } else {
    pts = routePrefix(progreso || 0);
    if (pos) pts.push(pos);
  }
  doneLine.setLatLngs(pts);
}

function placeTruck(pos, estado) {
  if (!pos) return;
  var delivered = estado === 'ENTREGADO';
  if (!truck) {
    truck = L.marker(pos, { icon: truckIcon(delivered), zIndexOffset: 1000 }).addTo(map);
  } else {
    truck.setLatLng(pos);
    truck.setIcon(truckIcon(delivered));
  }
  truck.bindTooltip(estado || '', { direction: 'top', offset: [0, -20] });
  lastPos = pos;
}

function showEnvio(e) {
  clearLayers();
  var ruta = e.ruta;
  if (ruta && ruta.puntos && ruta.puntos.length > 1) {
    routePts = ruta.puntos.map(function (p) { return [p[0], p[1]]; });
    cum = [0];
    for (var i = 1; i < routePts.length; i++) cum.push(cum[i - 1] + hav(routePts[i - 1], routePts[i]));
    routeLine = L.polyline(routePts, { color: '#94a3b8', weight: 7, opacity: 0.85 }).addTo(map);
    startMk = L.circleMarker(routePts[0], { radius: 7, color: '#334155', fillColor: '#ffffff', fillOpacity: 1, weight: 3 })
      .bindTooltip('Inicio').addTo(map);
    endMk = L.marker(routePts[routePts.length - 1], { icon: flagIcon }).bindTooltip('Destino').addTo(map);
  }
  doneLine = L.polyline([], { color: '#2563eb', weight: 7, opacity: 0.95 }).addTo(map);

  var pos = null;
  if (e.estado === 'ENTREGADO' && routePts.length) {
    pos = routePts[routePts.length - 1];
  } else if (e.posicion && e.posicion.latitude != null) {
    pos = [e.posicion.latitude, e.posicion.longitude];
  } else if (routePts.length) {
    pos = routePts[0];        /* aun no sale: el camion espera en el inicio */
  }
  setDone(e.progreso, (e.posicion && e.posicion.latitude != null) ? pos : null, e.estado);
  placeTruck(pos, e.estado);

  userMoved = false;
  map.invalidateSize(false);
  encuadrar();
  /* El WebView puede terminar su layout despues del snapshot: se reencuadra otra vez. */
  setTimeout(function () { map.invalidateSize(false); encuadrar(); }, 150);
}

/* Toda la ruta visible con margen (o el camion si no hay ruta). */
function encuadrar() {
  programmatic = true;
  if (routeLine) {
    map.fitBounds(routeLine.getBounds(), { padding: [48, 48], animate: false });
  } else if (lastPos) {
    map.setView(lastPos, 14, { animate: false });
  }
  programmatic = false;
}

function updatePosition(lat, lon, progreso, estado) {
  var pos;
  if (estado === 'ENTREGADO' && routePts.length) {
    pos = routePts[routePts.length - 1];     /* deja el camion en el destino */
  } else if (lat != null && lon != null) {
    pos = [lat, lon];
  } else {
    pos = lastPos;
  }
  setDone(progreso, lat != null ? pos : null, estado);
  placeTruck(pos, estado);
  if (pos && !map.getBounds().pad(-0.1).contains(pos)) map.panTo(pos);
}

function refrescarTamano() {
  map.invalidateSize(false);
  if (!userMoved) encuadrar();
}
