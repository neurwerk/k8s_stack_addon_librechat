SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
ADDON_TOOLING ?= $(WORKSPACE_ROOT)/tooling
CHART_DIRS := $(sort $(shell find charts -name Chart.yaml -printf '%h\n'))
PACKAGES := namespaces/librechat librechat/secret-sync librechat/database librechat/access librechat/oidc librechat/certificate-approval librechat/app

.PHONY: check
check:
	uv run --frozen --project "$(ADDON_TOOLING)" addon-check "$(CURDIR)"
	@for chart in $(CHART_DIRS); do \
		helm lint --strict "$$chart" --values tests/validation/helm-lint-values.yaml --set frontendLibrechat.enabled=true; \
		helm template test "$$chart" --values tests/validation/helm-lint-values.yaml --set frontendLibrechat.enabled=true | kubeconform -strict -summary -ignore-missing-schemas; \
	done
	@for package in $(PACKAGES); do \
		kustomize build --load-restrictor LoadRestrictionsNone "releases/$$package" | kubeconform -strict -summary -ignore-missing-schemas; \
	done
	uv run --frozen python -m unittest discover -s tests/charts -p 'test_*.py' -v
