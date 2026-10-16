.PHONY: test run demo api

test:
	uv run --offline pytest

run:
	uv run --offline itcguard --help

demo:
	uv run --offline itcguard reconcile --books fixtures/purchase_register.csv --gstr2b fixtures/gstr2b.csv --mapping fixtures/mappings/purchase_register.json --out reports

api:
	uv run --offline uvicorn itcguard.api:app --host 0.0.0.0 --port 8000
