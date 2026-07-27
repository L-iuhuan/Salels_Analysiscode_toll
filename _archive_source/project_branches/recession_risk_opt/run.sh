#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python pipeline.py
python generate_snapshot.py
