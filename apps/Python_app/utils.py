"""
utils.py
Ejecuta llamadas de red en un hilo aparte para no congelar la interfaz,
y entrega el resultado (o el error) de vuelta al hilo de Tkinter con
`after(0, ...)`, que es la unica forma segura de tocar widgets desde
otro hilo.
"""
import threading


def run_async(widget, fn, on_success=None, on_error=None):
    def trabajo():
        try:
            resultado = fn()
        except Exception as e:
            widget.after(0, lambda: on_error(e) if on_error else None)
            return
        widget.after(0, lambda: on_success(resultado) if on_success else None)

    threading.Thread(target=trabajo, daemon=True).start()
