.DEFAULT_GOAL := help
PYTHON ?= .venv/bin/python

.PHONY: help build init doctor start inspect check verify verify-go verify-native package

help:
	@printf '%s\n' 'Meeting Station — run from this repository root' '' 'make build    Build the standalone React interface' 'make init     Create private local configuration and tokens' 'make doctor   Inspect local model/application readiness' 'make start    Start the fully provisioned local application' 'make inspect  Explicit UI/archive inspection without ready models' 'make check    Check the harness and run its regression tests' 'make verify   Run all configured application/harness checks' 'make verify-go     Build retained UI and run all Go race tests' 'make verify-native Compile/test the retained macOS application' 'make package  Package a clean committed source revision'

build:
	VITE_MEETING_STATION=true VITE_MEETING_LOCAL=true npm --prefix web/frontend run build

init:
	$(PYTHON) scripts/run-local.py init

doctor:
	$(PYTHON) scripts/run-local.py doctor

start:
	$(PYTHON) scripts/run-local.py start

inspect:
	$(PYTHON) scripts/run-local.py start --allow-missing-models

check:
	python3 scripts/harness.py check
	python3 -m unittest discover -s tests -p 'test_*.py' -v

verify:
	python3 scripts/harness.py verify

verify-go:
	$(PYTHON) scripts/check-regressions.py go

verify-native:
	$(PYTHON) scripts/check-regressions.py native

package:
	$(PYTHON) scripts/package-submission.py
