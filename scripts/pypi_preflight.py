#!/usr/bin/env python3
"""Read-only PyPI collision preflight for an exact CORE release.

The preflight never uploads, authenticates or mutates a registry.  It returns
one of three useful states: a new project/version candidate, an existing
project with a free version, or a version collision that must block release.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SCHEMA = "core.pypi_preflight.v1"


def classify_project_metadata(metadata: object, version: str) -> dict[str, object]:
    """Classify a successful package-index response without network access."""

    if not isinstance(metadata, dict) or not isinstance(metadata.get("releases"), dict):
        return {
            "status": "blocked",
            "state": "malformed_registry_response",
            "errors": [{"code": "malformed_registry_response", "message": "Registry response lacks a releases object."}],
        }

    releases = metadata["releases"]
    if version in releases:
        return {
            "status": "blocked",
            "state": "collision",
            "errors": [{"code": "version_already_exists", "message": f"Version {version} already exists in the registry."}],
        }
    return {"status": "passed", "state": "version_available", "errors": []}


def _fetch_json(url: str) -> object:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "core-runtime-engine-release-preflight/11.6"})
    with urlopen(request, timeout=15) as response:  # noqa: S310 - URL is operator-selected registry metadata only
        return json.load(response)


def preflight(project: str, version: str, index_url: str) -> dict[str, object]:
    if not PROJECT_RE.fullmatch(project):
        return {
            "schema": SCHEMA,
            "status": "blocked",
            "state": "invalid_project_name",
            "project": project,
            "version": version,
            "errors": [{"code": "invalid_project_name", "message": "Project name contains unsupported characters."}],
            "network_used": False,
            "execution_authorized": False,
        }

    url = f"{index_url.rstrip('/')}/{project}/json"
    try:
        metadata = _fetch_json(url)
    except HTTPError as exc:
        if exc.code == 404:
            state = "project_absent_candidate"
            errors: list[dict[str, str]] = []
            status = "passed"
        else:
            state = "registry_unavailable"
            errors = [{"code": "registry_http_error", "message": f"Registry returned HTTP {exc.code}."}]
            status = "blocked"
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        state = "registry_unavailable"
        errors = [{"code": "registry_unavailable", "message": exc.__class__.__name__}]
        status = "blocked"
    else:
        classified = classify_project_metadata(metadata, version)
        state = str(classified["state"])
        errors = list(classified["errors"])  # type: ignore[arg-type]
        status = str(classified["status"])

    return {
        "schema": SCHEMA,
        "status": status,
        "state": state,
        "project": project,
        "version": version,
        "index_url": index_url.rstrip("/"),
        "errors": errors,
        "network_used": True,
        "execution_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a package-index version without publishing.")
    parser.add_argument("--project", default="core-runtime-engine")
    parser.add_argument("--version", required=True)
    parser.add_argument("--index-url", default="https://pypi.org/pypi")
    args = parser.parse_args(argv)
    result = preflight(args.project, args.version, args.index_url)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
