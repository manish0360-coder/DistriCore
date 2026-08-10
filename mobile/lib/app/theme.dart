import 'package:flutter/material.dart';

/// One theme, built for a phone held outdoors in daylight by someone in a hurry.
/// High contrast and large touch targets are a field requirement, not a preference.
ThemeData buildTheme() => ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF00695C)),
      useMaterial3: true,
      visualDensity: VisualDensity.comfortable,
    );
