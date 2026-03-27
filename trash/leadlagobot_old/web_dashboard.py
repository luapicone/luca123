from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / 'web'


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.path = '/web/index.html'
        return super().do_GET()


def main():
    os.chdir(ROOT)
    server = ThreadingHTTPServer(('0.0.0.0', 8080), DashboardHandler)
    print('LeadLagobot web dashboard on http://0.0.0.0:8080')
    server.serve_forever()


if __name__ == '__main__':
    main()
