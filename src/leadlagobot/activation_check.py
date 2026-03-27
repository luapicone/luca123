from pathlib import Path
from leadlagobot.config.settings import settings


def run_activation_check():
    results = {
        'real_execution_enabled': settings.real_execution_enabled,
        'dry_run_enabled': settings.dry_run_enabled,
        'has_real_confirm_token': bool(settings.real_confirm_token),
        'kill_switch_present': Path(settings.kill_switch_file).exists(),
        'has_binance_credentials': bool(settings.binance_api_key and settings.binance_api_secret),
        'has_bybit_credentials': bool(settings.bybit_api_key and settings.bybit_api_secret),
        'risk_enabled': settings.risk_enabled,
    }
    results['activation_ready'] = (
        results['real_execution_enabled']
        and not results['dry_run_enabled']
        and results['has_real_confirm_token']
        and not results['kill_switch_present']
        and results['risk_enabled']
    )
    return results


if __name__ == '__main__':
    import json
    print(json.dumps(run_activation_check(), indent=2))
