/// How a cached snapshot's age is written, in one place (P-8).
///
/// `YYYY-MM-DD HH:mm`, **always** — never a bare time. A shorter "09:14" would have to know
/// what *today* is, which means reading the device clock inside a widget: untestable, and a
/// value P-4 keeps off every path that matters. The date is also the honest form for a round
/// that may be a day old.
///
/// Lives in `core/` rather than beside one screen because both T5 and T6 show it, and a
/// screen importing another screen for a formatter is how a shared helper ends up with two
/// copies that drift.
String asOfLabel(DateTime asOf) {
  String two(int value) => value.toString().padLeft(2, '0');
  return '${asOf.year}-${two(asOf.month)}-${two(asOf.day)} '
      '${two(asOf.hour)}:${two(asOf.minute)}';
}
