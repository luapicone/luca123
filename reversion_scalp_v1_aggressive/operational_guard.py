"""
operational_guard.py

Capa de protección operativa para el loop live.
Responsabilidades:
  - Rastrear fallos consecutivos de exchange (open, close, fetch)
  - Activar pausa automática ante fallos repetidos
  - Kill switch por archivo en disco (KILL_SWITCH_FILE)
  - Alertas críticas escaladas por Discord cuando el bot se degrada
  - Proteger contra loops raros (ciclos sin sleep por excepciones)
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from reversion_scalp_v1_aggressive.config import LOG_PATH


# ---------------------------------------------------------------------------
# Configuración interna
# ---------------------------------------------------------------------------
_KILL_SWITCH_FILE       = Path(LOG_PATH.parent / 'KILL_SWITCH')
_MAX_CONSECUTIVE_ERRORS = 5       # fallos seguidos antes de pausa automática
_PAUSE_ON_ERROR_S       = 60      # segundos de pausa ante degradación
_CRITICAL_ALERT_EVERY_S = 120     # no spamear Discord con critical cada ciclo


class OperationalGuard:
    """
    Instancia por sesión. Se pasa al loop principal.
    Uso:

        guard = OperationalGuard(notify_fn=notify_discord_critical)

        # al inicio de cada ciclo:
        if not guard.check_ok():
            time.sleep(15)
            continue

        # al ocurrir un error de exchange:
        guard.record_error('open_order', symbol, exc)

        # al completarse un ciclo sin errores:
        guard.record_success()
    """

    def __init__(self, notify_fn=None):
        self._notify_fn            = notify_fn  # callable(msg: str) o None
        self._consecutive_errors   = 0
        self._last_critical_alert  = 0.0
        self._degraded_since       = None
        self._total_errors_session = 0

    # --- API pública ---

    def check_ok(self):
        """
        Devuelve True si el bot puede continuar operando.
        Devuelve False si:
          - existe el archivo KILL_SWITCH en disco
          - hay demasiados errores consecutivos (pausa automática)
        """
        if self._kill_switch_active():
            self._alert('KILL SWITCH activo — bot detenido. Eliminá el archivo KILL_SWITCH para reanudar.')
            return False

        if self._consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
            msg = (
                f'Bot en pausa automática: {self._consecutive_errors} errores consecutivos. '
                f'Degradado desde {self._degraded_since}. '
                f'Esperando {_PAUSE_ON_ERROR_S}s antes de reintentar.'
            )
            self._alert(msg)
            time.sleep(_PAUSE_ON_ERROR_S)
            # Reset para reintentar — si vuelve a fallar, se vuelve a pausar
            self._consecutive_errors = 0
            return False

        return True

    def record_error(self, context, symbol, exc):
        """
        Registra un fallo de exchange. Incrementa el contador de errores consecutivos.
        context: string describiendo qué falló ('open_order', 'close_order', 'fetch_ohlcv', etc.)
        """
        self._consecutive_errors   += 1
        self._total_errors_session += 1

        if self._degraded_since is None:
            self._degraded_since = datetime.now(timezone.utc).isoformat()

        logging.error(
            'operational_guard error context=%s symbol=%s consecutive=%s total_session=%s: %s',
            context, symbol, self._consecutive_errors, self._total_errors_session, exc
        )

        if self._consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
            self._alert(
                f'DEGRADACIÓN: {self._consecutive_errors} errores consecutivos en {context} '
                f'({symbol}). Último error: {exc}'
            )

    def record_success(self):
        """
        Registra un ciclo completamente exitoso (sin ningún error en el ciclo).
        Resetea el contador de errores consecutivos.
        Usar solo cuando el ciclo no llamó record_error() en ningún punto.
        """
        if self._consecutive_errors > 0:
            logging.info(
                'operational_guard: recovered after %s consecutive errors',
                self._consecutive_errors
            )
        self._consecutive_errors = 0
        self._degraded_since     = None

    def record_cycle_end(self, had_errors):
        """
        Alternativa más precisa a record_success().
        had_errors=True  → no resetea el contador (el ciclo tuvo al menos un error)
        had_errors=False → equivale a record_success()
        Usar esto en el loop principal en lugar de record_success() directo.
        """
        if had_errors:
            # El ciclo tuvo errores — no resetear, dejar que el contador acumule
            logging.debug('operational_guard: cycle ended with errors, consecutive=%s',
                          self._consecutive_errors)
        else:
            self.record_success()

    def is_degraded(self):
        return self._consecutive_errors > 0

    # --- Internos ---

    def _kill_switch_active(self):
        return _KILL_SWITCH_FILE.exists()

    def _alert(self, msg):
        """Loguea critical y notifica por Discord con throttling."""
        logging.critical('operational_guard: %s', msg)
        now = time.monotonic()
        if self._notify_fn and (now - self._last_critical_alert) > _CRITICAL_ALERT_EVERY_S:
            try:
                self._notify_fn(f'🚨 BOT ALERT: {msg}')
                self._last_critical_alert = now
            except Exception as exc:
                logging.error('operational_guard: notify failed: %s', exc)


# ---------------------------------------------------------------------------
# Helper para activar/desactivar el kill switch manualmente
# ---------------------------------------------------------------------------

def activate_kill_switch(reason='manual'):
    _KILL_SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KILL_SWITCH_FILE.write_text(
        f'activated_at={datetime.now(timezone.utc).isoformat()} reason={reason}\n'
    )
    logging.critical('KILL SWITCH activado: %s', reason)


def deactivate_kill_switch():
    if _KILL_SWITCH_FILE.exists():
        _KILL_SWITCH_FILE.unlink()
        logging.info('KILL SWITCH desactivado')