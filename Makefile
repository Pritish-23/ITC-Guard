.PHONY: test run demo

test:
	uv run --offline pytest

run:
	uv run --offline itcguard --help

demo:
	uv run --offline itcguard --help
