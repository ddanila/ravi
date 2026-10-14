.PHONY: test check

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v
	PYTHONPATH=src python3 examples/memory_monitor.py

check: test
	ruff check .
	ruff format --check .
