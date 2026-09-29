#!/usr/bin/env bash
# Full production hardening step from docs/SPECIFICATION.md §6.2: create an unprivileged
# `coderunner` OS user with no write access outside its per-execution temp dir, and disable
# its network access, so submitted student code runs fully isolated from the host.
#
# This requires root and is NOT needed to run the demo build in this repo — the code runner
# (backend/app/services/code_runner.py) already applies a timeout, stdout cap and memory rlimit
# without a dedicated OS user. Run this only when moving toward real students, then wire the
# runner to `sudo -u coderunner` (or migrate to per-run Docker/nsjail, as the spec suggests).

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash scripts/setup_runner_user.sh" >&2
  exit 1
fi

useradd --system --no-create-home --shell /usr/sbin/nologin coderunner 2>/dev/null || \
  echo "User 'coderunner' already exists"

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backend/runner_workdir"
mkdir -p "$WORKDIR"
chown coderunner:coderunner "$WORKDIR"
chmod 700 "$WORKDIR"

echo "coderunner user ready. Network restriction (e.g. via a firewall rule scoped to that"
echo "user, or 'unshare -n' per execution) is left as a follow-up per the spec."
