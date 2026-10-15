"""Print the OpenAPI schema, consumed by the front-end's generated client."""

import json
import sys

from nexus.entrypoints.api.app import create_app


def main() -> None:
    json.dump(create_app().openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
