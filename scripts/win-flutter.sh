#!/bin/sh
# Invoke a **Windows** Flutter launcher from WSL, and prove the path survived.
#
# WHY THIS EXISTS
#
# `adb.exe` can be named directly from a Makefile because it is a PE binary: WSL's
# binfmt_misc interop recognises it and hands it to Windows. `flutter.bat` is a batch
# script with no PE header, so the kernel falls through to the shell and bash reads the
# batch file as shell — `@ECHO: command not found`, one `$'\r'` per CRLF line, a syntax
# error at `FOR %%i IN`. Flutter ships no `flutter.exe`, so cmd.exe is the only route.
#
# WHY IT IS A SCRIPT AND NOT A MAKE VARIABLE
#
# On 2026-08-31 a gate run reached cmd.exe as
#
#     D:\chromeDownload\flutter_windows_3.44.7-stableflutter\bin\flutter.bat
#
# — the `\` before `flutter` gone. The Makefile expansion was reproduced under
# instrumented stubs and found byte-exact (`5c 66` present at both `\flutter` and
# `\flutter.bat`), so the loss is downstream of bash: WSL interop's command-line
# construction, cmd.exe's own parsing, or the reading of the process list. A Make variable
# cannot check its own expansion. This can, and does, before Flutter is launched.
#
# The cost of NOT checking is the expensive part: a wrong path makes `cmd /C` fail in a way
# that produced a thirty-minute apparent hang rather than an error. The checks below turn
# that into a named failure in well under a second.
#
# USAGE
#     FLUTTER_HOST=/mnt/d/.../flutter/bin/flutter.bat scripts/win-flutter.sh drive -d ...
#
# The caller's working directory is inherited by cmd.exe, so `cd mobile && …` still selects
# the Flutter project. POSIX sh on purpose: this runs from WSL and from the test container,
# and neither is guaranteed to be bash.

set -eu

# **`printf`, never `echo`.** POSIX `echo` interprets backslash escapes, and every string
# this script reports is a Windows path: `\c` truncates the rest of the line outright, `\f`
# becomes an invisible formfeed, `\b` a backspace that eats the preceding character. A
# diagnostic about a corrupted path that corrupts the path while printing it is worse than
# no diagnostic. Found by this script's own harness, printing `D:` and stopping at
# `\chromeDownload`.
die() {
	printf 'win-flutter: %s\n' "$1" >&2
	shift
	for line in "$@"; do printf '             %s\n' "$line" >&2; done
	exit 1
}

# ---------------------------------------------------------------- 1. the source path
[ "${FLUTTER_HOST:-}" ] || die "FLUTTER_HOST is not set." \
	"This script is invoked through \$(FLUTTER_HOST_RUN) in the Makefile, which sets it." \
	"To run it by hand:  FLUTTER_HOST=/mnt/<d>/.../flutter/bin/flutter.bat $0 --version"

[ -f "$FLUTTER_HOST" ] || die "No Windows Flutter launcher at: $FLUTTER_HOST" \
	"Point FLUTTER_HOST at flutter.bat, as a WSL path:" \
	"  make <target> FLUTTER_HOST=/mnt/<d>/path/to/flutter/bin/flutter.bat"

case "$FLUTTER_HOST" in
*" "*) die "FLUTTER_HOST contains a space: $FLUTTER_HOST" \
	"cmd.exe strips the quotes around a lone executable path, so a spaced path is split" \
	"at the space. Install Flutter to a space-free directory, or use the 8.3 short name" \
	"(cmd.exe /c dir /x shows it)." ;;
esac

# A control character renders as nothing, so a mangled override looks correct in every log
# and in `ps`. Checked on the INPUT, not on the translated path: it would survive translation
# into both sides of the component comparison below, which would then see two equal strings
# and pass. This is the one corruption that check cannot see.
if [ "$(printf '%s' "$FLUTTER_HOST" | LC_ALL=C tr -d '[:print:]' | wc -c)" -ne 0 ]; then
	die "FLUTTER_HOST contains a non-printing character and cannot be trusted." \
		"It will look correct in any log. Raw bytes:" \
		"$(printf '%s' "$FLUTTER_HOST" | od -c | head -4)"
fi

command -v wslpath >/dev/null || die "wslpath is not available." \
	"This script translates a WSL path to a Windows path and must run inside WSL."
command -v cmd.exe >/dev/null || die "cmd.exe is not reachable from this shell." \
	"A batch file cannot be executed by any Linux interpreter, so the Windows command" \
	"interpreter is required. Check /etc/wsl.conf -> [interop] enabled=true."

# ---------------------------------------------------------------- 2. the translation
WIN_FLUTTER=$(wslpath -w "$FLUTTER_HOST")

# ------------------------------------------------- 3. prove the translation lost nothing
#
# Both sides are reduced to a leading-slash component list: the WSL path loses its
# `/mnt/<letter>` mount prefix, the Windows path loses its `<letter>:` drive, and `\` becomes
# `/`. What remains must be identical. Deliberately not a substring test — `\flutter\bin`
# vanishing is invisible to a check that only looks for `flutter`, which is the whole defect.
src_tail=$(printf '%s' "$FLUTTER_HOST" | sed -E 's|^/mnt/[A-Za-z]||')
win_tail=$(printf '%s' "$WIN_FLUTTER" | sed -E 's|^[A-Za-z]:||' | tr '\\' '/')

[ "$src_tail" = "$win_tail" ] || die \
	"wslpath did not preserve the path. A component was lost or altered." \
	"  source : $FLUTTER_HOST" \
	"  windows: $WIN_FLUTTER" \
	"  expected components: $src_tail" \
	"  actual   components: $win_tail" \
	"$(printf '%s' "$WIN_FLUTTER" | od -c | head -4)"

# ------------------------------------ 4. prove the path SURVIVES the trip into cmd.exe
#
# The checks above are Linux-side and cannot see interop's command-line construction or
# cmd's parsing — the two layers the 2026-08-31 corruption must have come from. This probe
# crosses the same boundary the real call does, with the same argument, and asks Windows
# whether the file is there. It is the only check that can observe the reported failure.
if [ "$(cmd.exe /D /C if exist "$WIN_FLUTTER" echo PATH_OK 2>/dev/null | tr -d '\r\n')" \
	!= "PATH_OK" ]; then
	die "cmd.exe cannot see the launcher at the path it was handed." \
		"The path is correct on the Linux side, so it was altered crossing into Windows." \
		"  linux  : $FLUTTER_HOST" \
		"  handed : $WIN_FLUTTER" \
		"Compare the two below character by character — a lost separator is the known" \
		"failure (\`...-stableflutter\\bin\` instead of \`...-stable\\flutter\\bin\`):" \
		"$(printf '%s' "$WIN_FLUTTER" | od -c | head -4)"
fi

# ---------------------------------------------------------------------- 5. launch
#
# `call` is the correct mechanism for a batch file: without it cmd may hand control to the
# batch and never return the errorlevel that `mobile-device-kill` phase 1 asserts on — and
# that gate's check is INVERTED, so a lost exit code reads as a passing gate.
#
# `/D` suppresses `Command Processor\AutoRun`, whose own exit status would otherwise be
# able to become cmd's.
#
# `exec` so the gate waits on cmd.exe directly and signals reach it.
exec cmd.exe /D /C call "$WIN_FLUTTER" "$@"
