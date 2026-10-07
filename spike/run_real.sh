#!/usr/bin/env bash
# Real-model run of the spike: same model, same endpoint, three cells (pi, hermes, dotnet).
#
#   export SPIKE_BASE_URL=https://openrouter.ai/api/v1   # any OpenAI-compatible endpoint
#   export SPIKE_API_KEY=...
#   export SPIKE_MODELS="<cheap model id> <reference model id>"
#   export SPIKE_JUDGE_MODEL=<strong model, other family>  # optional: LLM judge (else score the blind sheet by hand)
#   ./run_real.sh [reps]                                   # default 5
#
# Prerequisites: see README.md (pi, hermes[mcp] on Python 3.14, .NET 10 SDK, Python venv with requirements.txt).
set -euo pipefail
cd "$(dirname "$0")"
REPS="${1:-5}"
SCENARIOS="reflection,noise,jobbby,gate,browser_gate"
: "${SPIKE_BASE_URL:?}" "${SPIKE_API_KEY:?}" "${SPIKE_MODELS:?space-separated model ids}"
export SPIKE_MCP_PYTHON="${SPIKE_MCP_PYTHON:-python3}"   # must have playwright installed for browser_gate

dotnet build dotnet/SpikeRunner.csproj -c Release -o dotnet/out -nologo -v quiet

for model in $SPIKE_MODELS; do
  tag="$(echo "$model" | tr '/:' '__')"
  SPIKE_MODEL="$model" python3 run_spike.py --mode real --reps "$REPS" --scenarios "$SCENARIOS" --tag "$tag" \
    | tee "results/console-real-$tag.txt"
  python3 common/judge.py export "results/runs-real-$tag.jsonl"
  if [ -n "${SPIKE_JUDGE_MODEL:-}" ]; then
    python3 common/judge.py judge "results/runs-real-$tag.jsonl" | tee "results/judge-report-$tag.md"
  fi
done
echo "Deterministic metrics: results/summary-real-<model>.md"
echo "Blind sheets for human scoring: results/blind-real-<model>.md (then: python3 common/judge.py report results/runs-real-<model>.jsonl scores.csv)"
