from dataclasses import dataclass

@dataclass
class BotState:
    balance: float = 20.0
    session_open_balance: float = 20.0
    session_peak_balance: float = 20.0
    consecutive_losses: int = 0
    reduced_size_trades_remaining: int = 0
    total_trades_today: int = 0
    wins_today: int = 0
    losses_today: int = 0
    total_trades_7d: int = 0
    wins_7d: int = 0
    hourly_volume: float = 0.0
    volume_7d_avg: float = 0.0
    is_halted: bool = False
    halt_reason: str | None = None
    halt_until: float | None = None
