F120_AUTHORITY ?=
export F120_AUTHORITY

.PHONY: check contracts test

# This target is developer ergonomics only. Release/P9 evidence invokes the
# independently accepted external launcher directly, because a Makefile inside
# the subject cannot establish authority over its own bytes.
check:
	@if [ -z "$$F120_AUTHORITY" ]; then \
		echo "refused: set F120_AUTHORITY to the absolute external f120-authority launcher" >&2; \
		exit 2; \
	fi
	@case "$$F120_AUTHORITY" in /*) ;; *) \
		echo "refused: F120_AUTHORITY must be absolute" >&2; exit 2 ;; esac
	@"$$F120_AUTHORITY" --subject "$(CURDIR)" check

contracts test:
	@echo "refused: contracts and tests are one authority transaction; run make check" >&2
	@exit 2
