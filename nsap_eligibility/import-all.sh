#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# NSAP Eligibility Predictor — watsonx Orchestrate Import Script
# Imports all tools and agents into the active Orchestrate environment
# ─────────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NSAP Eligibility Predictor — Orchestrate Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1: Import Python Tools ───────────────────────────────────────────────
echo ""
echo "[1/2] Importing Python tools..."

for tool in nsap_predictor.py nsap_scheme_details.py; do
  echo "  -> Importing tool: ${tool}"
  orchestrate tools import -k python -f "${SCRIPT_DIR}/tools/${tool}"
done

# ── Step 2: Import Agent ──────────────────────────────────────────────────────
echo ""
echo "[2/2] Importing agent..."

for agent in nsap_eligibility_agent.yaml; do
  echo "  -> Importing agent: ${agent}"
  orchestrate agents import -f "${SCRIPT_DIR}/agents/${agent}"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done! Run: orchestrate chat start"
echo "  Select agent: nsap_eligibility_agent"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
