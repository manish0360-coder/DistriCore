import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

/// Start-up, in one place.
///
/// Task 3 opens the database here and task 4 restores the session, **before** the first
/// frame — a shell that renders "signed out" and then corrects itself is how a user
/// discovers their outbox looks empty.
Future<void> bootstrap() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: DistriCoreApp()));
}
