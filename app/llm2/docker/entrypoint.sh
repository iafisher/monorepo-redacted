#!/usr/bin/env bash
set -euo pipefail

cd /workspace

if [[ ! -e .venv ]]; then
    ln -s /venv .venv
fi

export PATH="$HOME/.local/bin:$PATH"
./do env-sync

touch /workspace/.llm2_docker_ready
exec sleep infinity
