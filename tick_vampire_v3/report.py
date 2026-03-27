def format_session_report(payload: dict) -> str:
    return f"""
╔══════════════════════════════════════╗
║ TICK VAMPIRE v3 — SESSION LOG        ║
╠══════════════════════════════════════╣
║ Date/Time UTC : {payload.get('datetime')} ║
║ Session : {payload.get('session')} ║
║ Trades taken : {payload.get('trades')} ║
║ Wins / Losses : {payload.get('wins')} / {payload.get('losses')} ║
║ Win rate : {payload.get('wr')}% ║
║ Session PnL ($) : {payload.get('pnl')} ║
║ Session PnL (%) : {payload.get('pnl_pct')}% ║
║ Balance start : ${payload.get('start')} ║
║ Balance end : ${payload.get('end')} ║
║ Largest win : ${payload.get('best')} ║
║ Largest loss : ${payload.get('worst')} ║
║ Skipped signals : {payload.get('skipped')} ║
║ Halt triggered : {payload.get('halt')} ║
╚══════════════════════════════════════╝
""".strip()
