from dataclasses import dataclass
from leadlagobot.config.settings import settings


@dataclass
class SymbolRules:
    symbol: str
    tick_size: float
    qty_step: float
    min_qty: float
    min_notional: float
    max_leverage: float = 1.0


DEFAULT_RULES = {
    symbol: SymbolRules(
        symbol=symbol,
        tick_size=0.0001,
        qty_step=0.001,
        min_qty=0.001,
        min_notional=5.0,
        max_leverage=1.0,
    )
    for symbol in settings.symbols
}


ACTIVE_RULES = DEFAULT_RULES.copy()


def update_rules(metadata: dict[str, object]):
    for symbol, item in metadata.items():
        ACTIVE_RULES[symbol] = SymbolRules(
            symbol=symbol,
            tick_size=float(getattr(item, 'tick_size', 0.0001)),
            qty_step=float(getattr(item, 'qty_step', 0.001)),
            min_qty=float(getattr(item, 'min_qty', 0.001)),
            min_notional=float(getattr(item, 'min_notional', 5.0)),
            max_leverage=1.0,
        )


def round_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return (value // step) * step


def validate_symbol_rules(symbol: str, price: float, requested_qty: float):
    rules = ACTIVE_RULES.get(symbol)
    if not rules:
        return False, 'unknown_symbol_rules', None

    qty = round_to_step(requested_qty, rules.qty_step)
    notional = qty * price

    if qty < rules.min_qty:
        return False, 'qty_below_min_qty', rules
    if notional < rules.min_notional:
        return False, 'notional_below_min_notional', rules
    return True, 'ok', rules
