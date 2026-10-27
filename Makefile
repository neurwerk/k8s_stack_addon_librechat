SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := check
TOOLING := uv run --locked --project tooling
TOOLING_IMAGE := ghcr.io/neurwerk/k8s-stack-addon-librechat-tooling
BASE_REPO ?=
CHART_DIRS := $(sort $(shell find charts -name Chart.yaml -printf '%h\n'))

.PHONY: check tooling-check tooling-build
tooling-check:
	$(TOOLING) ruff check --config tooling/pyproject.toml tooling
	$(TOOLING) ruff format --check --config tooling/pyproject.toml tooling
	$(TOOLING) ty check --project tooling
	BASE_REPO="$(BASE_REPO)" $(TOOLING) pytest tooling/tests

tooling-build:
	@test -n "$(VERSION)" -a -n "$(REVISION)" || { echo 'Set VERSION and REVISION for image metadata'; exit 1; }
	docker build --build-arg VERSION="$(VERSION)" --build-arg REVISION="$(REVISION)" -t "$(TOOLING_IMAGE):$(VERSION)" tooling

check: tooling-check
	@test -n "$(BASE_REPO)" || { echo 'Set BASE_REPO to the exact selected Base checkout'; exit 1; }
	$(TOOLING) addon-check "$(CURDIR)" --base "$(BASE_REPO)"
	@for chart in $(CHART_DIRS); do \
		helm lint --strict "$$chart" --values tests/validation/helm-lint-values.yaml --set frontendLibrechat.enabled=true; \
		helm template test "$$chart" --values tests/validation/helm-lint-values.yaml --set frontendLibrechat.enabled=true | kubeconform -strict -summary -ignore-missing-schemas; \
	done
	@packages="$$($(TOOLING) python -c 'from pathlib import Path; from k8s_stack_tooling.addons import load_manifest; print(" ".join(p.path for p in load_manifest(Path("release/manifest.yaml")).spec.packages))')"; \
	for package in $$packages; do \
		kustomize build --load-restrictor LoadRestrictionsNone "$$package" | kubeconform -strict -summary -ignore-missing-schemas; \
	done
	uv run --frozen python -m unittest discover -s tests/charts -p 'test_*.py' -v
