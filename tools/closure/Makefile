UV ?= uv

.PHONY: check contracts test

contracts:
	sha256sum -c SHA256SUMS
	$(UV) run --locked python contracts/validate_f120.py --self-test

test:
	$(UV) run --locked python -m unittest discover -s tests -v

check: contracts test
