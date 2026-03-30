from dataclasses import dataclass, field


@dataclass
class BotState:
    balance: float
    daily_start_balance: float
    session_peak_balance: float
    trades_today: int = 0
    consecutive_losses: int = 0
    pause_until: float | None = None
    symbol_cooldowns: dict = field(default_factory=dict)
