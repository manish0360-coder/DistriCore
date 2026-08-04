#!/usr/bin/env python
"""Django management entrypoint."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django is not importable. The application runs only inside Docker (FD-02); "
            "try `make shell` rather than a host interpreter."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
