.PHONY: test run demo api ui

UV_RUN = UV_LINK_MODE=copy uv run --offline

test:
	$(UV_RUN) pytest

run:
	$(UV_RUN) itcguard --help

demo:
	$(UV_RUN) itcguard reconcile --books fixtures/purchase_register.csv --gstr2b fixtures/gstr2b.csv --mapping fixtures/mappings/purchase_register.json --out reports

api:
	$(UV_RUN) uvicorn itcguard.api:app --host 0.0.0.0 --port 8000

ui:
	$(UV_RUN) streamlit run src/itcguard/ui.py
