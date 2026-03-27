from leadlagobot.config.settings import settings


class MarginValidator:
    def validate(self, balance: float, current_exposure_usd: float, requested_notional_usd: float):
        available = balance - current_exposure_usd
        if requested_notional_usd > available:
            return False, 'insufficient_available_balance'
        if current_exposure_usd + requested_notional_usd > settings.max_exposure_usd:
            return False, 'exposure_limit_reached'
        return True, 'ok'
