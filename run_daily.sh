#!/bin/zsh
# Daily entry point for launchd. When the Mac was asleep at the scheduled time, launchd
# fires the job right after wake — before Wi-Fi/VPN and LM Studio are ready. Wait for
# both (up to ~3 min each) before running Pheme.
cd "$(dirname "$0")" || exit 1

echo "===== $(date '+%Y-%m-%d %H:%M:%S') run_daily.sh ====="

for _ in {1..36}; do
    curl -s --max-time 5 -o /dev/null https://hn.algolia.com && break
    sleep 5
done

if grep -q '^LLM_PROVIDER=local' .env 2>/dev/null; then
    base_url=$(grep '^LLM_BASE_URL=' .env | cut -d= -f2- | sed 's#/v1/*$##')
    for _ in {1..36}; do
        curl -s --max-time 5 -o /dev/null "${base_url:-http://localhost:1234}/api/v0/models" && break
        sleep 5
    done
fi

exec .venv/bin/python main.py
