#!/data/data/com.termux/files/usr/bin/bash
# Run live integration tests against a real Petagent server on nubia.
# Usage: bash run_live_tests.sh

set -e

cd "$(dirname "$0")/.."

export PETAGENT_DATA_DIR="${PETAGENT_DATA_DIR:-/data/data/com.termux/files/home/petagent-data}"
PORT=9821
export PETAGENT_TEST_URL="http://127.0.0.1:$PORT"

mkdir -p "$PETAGENT_DATA_DIR"

echo "=== Starting Petagent server on port $PORT ==="
../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
SERVER_PID=$!

cleanup() {
    echo ""
    echo "=== Stopping server (PID $SERVER_PID) ==="
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for server to be ready
echo -n "Waiting for server"
for i in $(seq 1 30); do
    if curl -s "$PETAGENT_TEST_URL/api/health" > /dev/null 2>&1; then
        echo " ready!"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "=== Running live integration tests ==="
echo ""
../.venv/bin/python -m pytest tests/test_live_nubia.py -v --tb=short
