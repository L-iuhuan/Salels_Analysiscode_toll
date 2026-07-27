#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python run_all.py --stage silver,product,customer,kpi,cross_ref
