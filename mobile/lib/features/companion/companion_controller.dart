import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/failure.dart';
import '../../domain/companion/companion.dart';
import 'companion_providers.dart';

final companionProvider =
    NotifierProvider<CompanionController, CompanionState>(CompanionController.new);

/// The four Companion sections, in the order the tabs present them.
enum CompanionSection { today, pending, receivables, attention }

/// What the Companion screens draw themselves from.
///
/// **One state for four sections, with per-section loading.** They share a refresh and a
/// message channel, and holding four independent notifiers would mean four copies of the same
/// failure-to-prose mapping — the drift `_messageFor` exists in one place to prevent.
@immutable
final class CompanionState {
  const CompanionState({
    this.section = CompanionSection.today,
    this.loading = const {},
    this.dashboard,
    this.pending = const [],
    this.receivables,
    this.attention,
    this.message,
  });

  /// Which section the shell is showing.
  final CompanionSection section;

  /// The sections with a request in flight. A set rather than a bool: switching sections
  /// while one is loading must not make the other look busy.
  final Set<CompanionSection> loading;

  /// `null` until the first successful load — **distinct from an empty result**. A dashboard
  /// that has never loaded and a dashboard of zeroes are different claims, and only the
  /// second one is news.
  final Dashboard? dashboard;

  final List<CompanionDelivery> pending;
  final ReceivablesSummary? receivables;
  final AttentionBoard? attention;

  /// User-visible, client-owned prose. Never a raw server `detail` — `05` §5 permits
  /// rewording `title` and `detail`, so a screen that rendered them is a screen a copy-edit
  /// can break.
  final String? message;

  bool isLoading(CompanionSection section) => loading.contains(section);

  CompanionState copyWith({
    CompanionSection? section,
    Set<CompanionSection>? loading,
    Dashboard? dashboard,
    List<CompanionDelivery>? pending,
    ReceivablesSummary? receivables,
    AttentionBoard? attention,
    String? message,
    bool clearMessage = false,
  }) =>
      CompanionState(
        section: section ?? this.section,
        loading: loading ?? this.loading,
        dashboard: dashboard ?? this.dashboard,
        pending: pending ?? this.pending,
        receivables: receivables ?? this.receivables,
        attention: attention ?? this.attention,
        message: clearMessage ? null : (message ?? this.message),
      );
}

/// Owner Companion Mode's decisions, with no widget in them (M8 §3.4).
///
/// **Every method here reads.** §3.4's boundary table forbids writing anything, and the port
/// this controller holds offers nothing to write with — so there is no `confirm`, no
/// `dispatch`, no `retry`. A button that appeared to act would be admin logic wearing a
/// Companion label, and `02A` §9.3 means hiding it would not be a control anyway.
final class CompanionController extends Notifier<CompanionState> {
  @override
  CompanionState build() => const CompanionState();

  /// Show a section and load it if it has not been loaded yet.
  ///
  /// Lazy rather than eager: fetching all four on entry would spend four round trips on 2G to
  /// populate three screens the owner may not open.
  Future<void> show(CompanionSection section) async {
    state = state.copyWith(section: section, clearMessage: true);
    if (_isLoaded(section)) return;
    await load(section);
  }

  bool _isLoaded(CompanionSection section) => switch (section) {
        CompanionSection.today => state.dashboard != null,
        // An empty pending list is a loaded pending list; `attention` and `receivables`
        // carry their own "never loaded" nullability for the same reason.
        CompanionSection.pending => state.pending.isNotEmpty,
        CompanionSection.receivables => state.receivables != null,
        CompanionSection.attention => state.attention != null,
      };

  /// Fetch one section. Safe to call again — a refresh is exactly this.
  Future<void> load(CompanionSection section) async {
    if (state.isLoading(section)) return;
    state = state.copyWith(loading: {...state.loading, section}, clearMessage: true);

    final repository = ref.read(companionPortProvider);
    final state0 = state;

    switch (section) {
      case CompanionSection.today:
        final result = await repository.dashboard();
        state = result.fold(
          (value) => _settled(section, state0.copyWith(dashboard: value)),
          (failure) => _failed(section, failure),
        );
      case CompanionSection.pending:
        final result = await repository.pendingDeliveries();
        state = result.fold(
          (value) => _settled(section, state0.copyWith(pending: value)),
          (failure) => _failed(section, failure),
        );
      case CompanionSection.receivables:
        final result = await repository.receivables();
        state = result.fold(
          (value) => _settled(section, state0.copyWith(receivables: value)),
          (failure) => _failed(section, failure),
        );
      case CompanionSection.attention:
        final result = await repository.needsAttention();
        state = result.fold(
          (value) => _settled(section, state0.copyWith(attention: value)),
          (failure) => _failed(section, failure),
        );
    }
  }

  /// Reload whichever section is on screen. What pull-to-refresh calls.
  Future<void> refresh() => load(state.section);

  CompanionState _settled(CompanionSection section, CompanionState next) =>
      next.copyWith(loading: _without(section), clearMessage: true);

  /// **A failed load leaves the previous data in place**, and says so.
  ///
  /// Blanking the screen on a dropped connection would replace a figure that was true a
  /// minute ago with nothing at all — worse than showing it beside a message, which is the
  /// same judgement `SyncStatusController` makes about the local counts.
  CompanionState _failed(CompanionSection section, Failure failure) =>
      state.copyWith(loading: _without(section), message: _messageFor(failure));

  Set<CompanionSection> _without(CompanionSection section) =>
      {...state.loading}..remove(section);

  /// `Failure` is sealed, so this is exhaustive at compile time.
  String _messageFor(Failure failure) => switch (failure) {
        Offline() => 'No connection. Companion Mode needs one to show live figures.',
        Unauthenticated() => 'Your session has ended. Please sign in again.',
        // `_internal` admits OWNER, SALESMAN and DELIVERY, so a 403 here means the account
        // lost its role rather than that the tab was drawn wrongly — worth saying plainly.
        Refused(:final code) when code == 'PERMISSION_DENIED' =>
          'This account is not allowed to see these figures.',
        MalformedResponse() => 'The server sent something we could not read.',
        CertificateRejected() => "Can't verify this server. Contact the office if this continues.",
        // Reachable only through a local read, which this screen never makes. Named rather
        // than defaulted, because `Failure` is sealed and a new member should fan out here.
        StorageFull() => 'Not enough storage to load this.',
        Refused() || ProblemFailure() => 'That could not be loaded. Try again.',
      };
}
