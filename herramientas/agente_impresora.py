#!/usr/bin/env python3
"""
Agente local de impresión — Adelé Boutique POS
Impresora: Qian QOP-T80UL-RI-0 (ESC/POS, 80 mm)

Corre en la Mac/Windows del punto de venta.  El navegador le envía los
bytes ESC/POS que obtuvo del servidor Django y el agente los reenvía a
la impresora (Ethernet o USB).

Uso rápido
----------
  # Ethernet (recomendado — más estable):
  python agente_impresora.py --modo ethernet --ip 192.168.1.100

  # USB en Mac (la impresora aparece como cola CUPS):
  python agente_impresora.py --modo usb --nombre-cola "QOP-T80UL"

  # USB en Windows (puerto serie COM):
  python agente_impresora.py --modo windows --puerto COM3

  # Solo para probar la conexión:
  python agente_impresora.py --modo ethernet --ip 192.168.1.100 --test

Dependencias (ya incluidas en requirements.txt del proyecto):
  python-escpos==3.1

Instalación en Mac (una vez):
  cd herramientas
  pip install python-escpos
  python agente_impresora.py --modo ethernet --ip <IP-DE-TU-IMPRESORA>

Encontrar la IP de la impresora:
  Imprime una auto-prueba: mantén presionado FEED al encender.
  La impresora imprime su IP en el papel.
"""

import argparse
import json
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PUERTO_AGENTE = 19191   # puerto local donde escucha el agente


# ── Envío a impresora ─────────────────────────────────────────────────────────

def enviar_ethernet(data: bytes, ip: str, puerto: int = 9100) -> None:
    """Envía raw ESC/POS a la impresora vía TCP (puerto 9100)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect((ip, puerto))
        s.sendall(data)


def enviar_usb_mac(data: bytes, nombre_cola: str) -> None:
    """
    Envía raw ESC/POS via CUPS en Mac.
    Nombre de cola: ver 'lpstat -p' o Preferencias del Sistema > Impresoras.
    """
    proc = subprocess.run(
        ['lpr', '-P', nombre_cola, '-l'],  # -l = raw (sin filtros CUPS)
        input=data,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"lpr falló: {proc.stderr.decode().strip()}")


def enviar_windows(data: bytes, puerto_com: str) -> None:
    """Envía raw ESC/POS al puerto serie en Windows (COM1, COM3, etc.)."""
    with open(f'\\\\.\\{puerto_com}', 'wb') as f:
        f.write(data)


# ── Servidor HTTP local ───────────────────────────────────────────────────────

class ManejadorImpresion(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path not in ('/imprimir', '/imprimir/'):
            self._json(404, {'error': 'Ruta no encontrada'})
            return

        length = int(self.headers.get('Content-Length', 0))
        data   = self.rfile.read(length)
        if not data:
            self._json(400, {'error': 'Sin datos'})
            return

        try:
            self.server.enviar(data)
            self._json(200, {'ok': True, 'bytes': len(data)})
            print(f"[✓] {len(data)} bytes enviados a la impresora")
        except Exception as exc:
            print(f"[✗] Error al imprimir: {exc}")
            self._json(500, {'error': str(exc)})

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def _cors(self) -> None:
        # Permite que el navegador (origen del POS en Railway) haga POST local
        self.send_header('Access-Control-Allow-Origin',  '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, fmt, *args):  # silenciar peticiones OPTIONS ruidosas
        if self.command != 'OPTIONS':
            print(f"  {self.address_string()} → {fmt % args}")


class ServidorImpresion(HTTPServer):
    """Extiende HTTPServer para inyectar la función `enviar` de la impresora."""

    def __init__(self, fn_enviar, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enviar = fn_enviar


# ── Test de conexión ──────────────────────────────────────────────────────────

def test_impresora(fn_enviar) -> None:
    """Imprime texto de prueba y corta el papel."""
    ESC, GS = b'\x1b', b'\x1d'
    INIT = ESC + b'@'
    BOLD_ON  = ESC + b'E\x01'
    BOLD_OFF = ESC + b'E\x00'
    FEED     = ESC + b'd\x04'         # avanza 4 líneas
    CORTE    = GS  + b'V\x00'         # corte completo

    data = (
        INIT
        + BOLD_ON
        + 'ADELÉ BOUTIQUE — TEST\n'.encode('utf-8')
        + BOLD_OFF
        + 'Impresora Qian QOP-T80UL-RI-0\n'.encode('utf-8')
        + 'Agente de impresión OK\n'.encode('utf-8')
        + FEED
        + CORTE
    )
    fn_enviar(data)
    print("[✓] Página de prueba enviada. Si no salió papel, revisa la conexión.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Agente local de impresión para Adelé Boutique POS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--modo', choices=['ethernet', 'usb', 'windows'],
                        default='ethernet',
                        help='Modo de conexión con la impresora (default: ethernet)')
    parser.add_argument('--ip',           default='',    help='IP de la impresora (modo ethernet)')
    parser.add_argument('--puerto-impr',  default=9100,  type=int,
                        help='Puerto TCP de la impresora (default: 9100)')
    parser.add_argument('--nombre-cola',  default='',
                        help='Nombre de la cola CUPS en Mac (modo usb)')
    parser.add_argument('--puerto',       default='COM1',
                        help='Puerto COM en Windows (modo windows)')
    parser.add_argument('--puerto-agente', default=PUERTO_AGENTE, type=int,
                        help=f'Puerto local del agente (default: {PUERTO_AGENTE})')
    parser.add_argument('--test', action='store_true',
                        help='Imprime una página de prueba y sale')
    args = parser.parse_args()

    # Construir función de envío según modo
    if args.modo == 'ethernet':
        if not args.ip:
            parser.error('--ip es obligatorio en modo ethernet')
        fn_enviar = lambda data: enviar_ethernet(data, args.ip, args.puerto_impr)
        destino = f"Ethernet {args.ip}:{args.puerto_impr}"

    elif args.modo == 'usb':
        if not args.nombre_cola:
            parser.error('--nombre-cola es obligatorio en modo usb (ver: lpstat -p)')
        fn_enviar = lambda data: enviar_usb_mac(data, args.nombre_cola)
        destino = f"CUPS '{args.nombre_cola}'"

    else:  # windows
        fn_enviar = lambda data: enviar_windows(data, args.puerto)
        destino = f"Puerto {args.puerto}"

    if args.test:
        print(f"Enviando página de prueba a {destino}...")
        try:
            test_impresora(fn_enviar)
        except Exception as exc:
            print(f"[✗] Error: {exc}")
            sys.exit(1)
        sys.exit(0)

    # Iniciar servidor
    direccion = ('127.0.0.1', args.puerto_agente)
    servidor  = ServidorImpresion(fn_enviar, direccion, ManejadorImpresion)

    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  Agente de impresión — Adelé Boutique POS        ║")
    print(f"╠══════════════════════════════════════════════════╣")
    print(f"║  Impresora : {destino:<37}║")
    print(f"║  Escuchando: http://localhost:{args.puerto_agente}            ║")
    print(f"║  Ctrl+C para detener                             ║")
    print(f"╚══════════════════════════════════════════════════╝")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n[✓] Agente detenido.")


if __name__ == '__main__':
    main()
