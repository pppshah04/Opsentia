"""Live Server Smoke Test Script (Manual Integration Testing).
Run against an actively listening server (e.g., http://127.0.0.1:8000).
"""
import requests

base = 'http://127.0.0.1:8000'

def main():
    print(f"Testing live server at {base}...")
    try:
        r_boot = requests.get(f'{base}/api/ui/bootstrap?queue=Queue+A&as_of=2026-09-13+17:00:00', timeout=5)
        print('Bootstrap status:', r_boot.status_code)
        data = r_boot.json()
        daily = data.get('daily', [])
        print('Daily rows:', len(daily), 'last day is_partial:', daily[-1].get('is_partial') if daily else None)
        fc = data.get('full_day_forecast', {})
        print('Forecast keys:', list(fc.keys()))
        print('Watchouts count:', len(data.get('watchouts', [])))

        r_an = requests.get(f'{base}/api/analytics?queue=All+Queues&grain=week&as_of=2026-09-13+17:00:00', timeout=5)
        print('Analytics All Queues week:', r_an.status_code, len(r_an.json().get('series', [])))

        r_bt = requests.get(f'{base}/api/forecasts/full-day/backtest?queue=Queue+A&as_of=2026-09-13+17:00:00&eval_days=5', timeout=5)
        print('Forecast backtest:', r_bt.status_code, 'MAE:', r_bt.json().get('mean_absolute_error_sla_pp'))

        r_c = requests.post(f'{base}/api/assistant/chat', json={'message': 'Why is SLA falling today on Queue A?', 'queue': 'Queue A', 'as_of': '2026-09-13 17:00:00'}, timeout=5)
        print('Chat response status:', r_c.status_code, 'tools:', len(r_c.json().get('tool_calls', [])))
        print('Chat answer preview:', r_c.json().get('answer', '')[:140])
        print("Live server smoke test completed successfully.")
    except Exception as e:
        print(f"Live server connection error: {e}")

if __name__ == '__main__':
    main()
