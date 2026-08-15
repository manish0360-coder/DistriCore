# The M8 toolchain image (M8 task 1).
#
# **Why we build this rather than pull one.**
# The first attempt used `ghcr.io/cirruslabs/flutter:$(FLUTTER_VERSION)`. That image does
# not exist and never will: cirruslabs/docker-images-flutter states *"This repository will
# stop updating images starting May 1st 2026 due to Cirrus Labs winding down operations
# after an acquisition"*, and Flutter 3.44.0 shipped on 18 May 2026 — after the cutoff.
# Their Docker Hub predecessor `cirrusci/flutter` stopped at 3.7.7 in March 2023.
#
# A pinned toolchain that depends on a third party continuing to publish is not pinned; it
# is borrowed. This installs the SDK from Google's own release archive, which is the same
# trust level as `python:3.12-slim-bookworm` above it, and it is the reasoning that closed
# TD-21 applied to the second toolchain.
#
# Base pinned to the same Debian release as the backend runtime, so both toolchains move
# together or not at all.
FROM debian:bookworm-slim

# Supplied by the Makefile from `mobile/.flutter-version` — the single pin. There is
# deliberately no default: a toolchain image that guesses its own version is the defect
# this file exists to fix.
ARG FLUTTER_VERSION
# Optional today, required once known (TD-38). A version pins *which release*; a checksum
# pins *which bytes*. `uv.lock` gives the Python side the second guarantee; until this is
# filled in, the mobile side has only the first.
ARG FLUTTER_SHA256=""

# `git` is not a convenience: the flutter tool shells out to it for its own version
# resolution and refuses to start without it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        # Drift's `NativeDatabase` opens the system SQLite when `flutter test` runs on the
        # Dart VM — there is no device to supply `sqlcipher_flutter_libs`. Without this the
        # outbox tests fail on a missing `libsqlite3.so`, which reads like broken code and
        # is broken plumbing (task 3).
        libsqlite3-0 \
        unzip \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN test -n "$FLUTTER_VERSION" \
      || { echo "FLUTTER_VERSION build-arg is required; it comes from mobile/.flutter-version"; exit 1; } \
    && curl -fsSL -o /tmp/flutter.tar.xz \
        "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
    && if [ -n "$FLUTTER_SHA256" ]; then \
         echo "${FLUTTER_SHA256}  /tmp/flutter.tar.xz" | sha256sum -c -; \
       else \
         echo "WARNING: FLUTTER_SHA256 unset — version pinned, bytes not (TD-38)."; \
         echo "  sha256: $(sha256sum /tmp/flutter.tar.xz | cut -d' ' -f1)"; \
       fi \
    && tar -xJf /tmp/flutter.tar.xz -C /opt \
    && rm /tmp/flutter.tar.xz

# `HOME` and `PUB_CACHE` point at world-writable paths because the containers run as the
# *developer's* uid (see `FLUTTER_RUN` in the Makefile) so that `pubspec.lock` and
# `.dart_tool/` land in the working tree owned by them, not by root. `make lock` solved the
# same problem the same way for uv.
ENV PATH="/opt/flutter/bin:/opt/flutter/bin/cache/dart-sdk/bin:${PATH}" \
    PUB_CACHE=/tmp/pub-cache \
    HOME=/tmp \
    FLUTTER_SUPPRESS_ANALYTICS=true

# Materialise the bundled Dart SDK and the flutter_tools snapshot at *build* time, then
# open the permissions. Without this, the first `flutter pub get` as a non-root uid would
# try to write into a root-owned /opt/flutter and fail — on the developer's machine, not
# here, which is the worst place to discover it.
#
# `--system` rather than `--global`: the global config lives in $HOME, which differs
# between the build (root) and the run (an arbitrary uid).
RUN git config --system --add safe.directory /opt/flutter \
    && mkdir -p /tmp/pub-cache \
    && flutter --version \
    && chmod -R a+rwX /opt/flutter /tmp/pub-cache

# No ENTRYPOINT. The Makefile supplies the whole command, exactly as `make lock` does for
# the uv image — where a missing ENTRYPOINT once turned `uv lock` into `exec: "lock"`.
