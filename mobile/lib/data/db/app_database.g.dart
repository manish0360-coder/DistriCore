// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'app_database.dart';

// ignore_for_file: type=lint
class $OutboxOperationsTable extends OutboxOperations
    with TableInfo<$OutboxOperationsTable, OutboxRow> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $OutboxOperationsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _sequenceMeta = const VerificationMeta(
    'sequence',
  );
  @override
  late final GeneratedColumn<int> sequence = GeneratedColumn<int>(
    'sequence',
    aliasedName,
    false,
    hasAutoIncrement: true,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
    defaultConstraints: GeneratedColumn.constraintIsAlways(
      'PRIMARY KEY AUTOINCREMENT',
    ),
  );
  static const VerificationMeta _clientUuidMeta = const VerificationMeta(
    'clientUuid',
  );
  @override
  late final GeneratedColumn<String> clientUuid = GeneratedColumn<String>(
    'client_uuid',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
    defaultConstraints: GeneratedColumn.constraintIsAlways('UNIQUE'),
  );
  static const VerificationMeta _operationTypeMeta = const VerificationMeta(
    'operationType',
  );
  @override
  late final GeneratedColumn<String> operationType = GeneratedColumn<String>(
    'operation_type',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _clientCreatedAtMeta = const VerificationMeta(
    'clientCreatedAt',
  );
  @override
  late final GeneratedColumn<String> clientCreatedAt = GeneratedColumn<String>(
    'client_created_at',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _payloadMeta = const VerificationMeta(
    'payload',
  );
  @override
  late final GeneratedColumn<String> payload = GeneratedColumn<String>(
    'payload',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _statusMeta = const VerificationMeta('status');
  @override
  late final GeneratedColumn<String> status = GeneratedColumn<String>(
    'status',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  @override
  List<GeneratedColumn> get $columns => [
    sequence,
    clientUuid,
    operationType,
    clientCreatedAt,
    payload,
    status,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'outbox_operation';
  @override
  VerificationContext validateIntegrity(
    Insertable<OutboxRow> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('sequence')) {
      context.handle(
        _sequenceMeta,
        sequence.isAcceptableOrUnknown(data['sequence']!, _sequenceMeta),
      );
    }
    if (data.containsKey('client_uuid')) {
      context.handle(
        _clientUuidMeta,
        clientUuid.isAcceptableOrUnknown(data['client_uuid']!, _clientUuidMeta),
      );
    } else if (isInserting) {
      context.missing(_clientUuidMeta);
    }
    if (data.containsKey('operation_type')) {
      context.handle(
        _operationTypeMeta,
        operationType.isAcceptableOrUnknown(
          data['operation_type']!,
          _operationTypeMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_operationTypeMeta);
    }
    if (data.containsKey('client_created_at')) {
      context.handle(
        _clientCreatedAtMeta,
        clientCreatedAt.isAcceptableOrUnknown(
          data['client_created_at']!,
          _clientCreatedAtMeta,
        ),
      );
    } else if (isInserting) {
      context.missing(_clientCreatedAtMeta);
    }
    if (data.containsKey('payload')) {
      context.handle(
        _payloadMeta,
        payload.isAcceptableOrUnknown(data['payload']!, _payloadMeta),
      );
    } else if (isInserting) {
      context.missing(_payloadMeta);
    }
    if (data.containsKey('status')) {
      context.handle(
        _statusMeta,
        status.isAcceptableOrUnknown(data['status']!, _statusMeta),
      );
    } else if (isInserting) {
      context.missing(_statusMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {sequence};
  @override
  OutboxRow map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return OutboxRow(
      sequence: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}sequence'],
      )!,
      clientUuid: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}client_uuid'],
      )!,
      operationType: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}operation_type'],
      )!,
      clientCreatedAt: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}client_created_at'],
      )!,
      payload: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}payload'],
      )!,
      status: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}status'],
      )!,
    );
  }

  @override
  $OutboxOperationsTable createAlias(String alias) {
    return $OutboxOperationsTable(attachedDatabase, alias);
  }
}

class OutboxRow extends DataClass implements Insertable<OutboxRow> {
  /// **D-C1.** Drift's `autoIncrement()` emits `INTEGER PRIMARY KEY AUTOINCREMENT`, which
  /// is the whole decision: plain `INTEGER PRIMARY KEY` assigns `max(rowid) + 1`, so
  /// purging the highest acknowledged row would **reissue a value already used** and break
  /// the ordering guarantee. `AUTOINCREMENT` is the only SQLite construct that forbids
  /// reuse, and §5.3 requires that purge.
  final int sequence;

  /// **P-6 / C-2 / AD-09.** Unique because I-6 is explicit that the guarantee is *"a
  /// database unique constraint, not an application check — a concurrent double-submit
  /// would defeat an application check."*
  final String clientUuid;
  final String operationType;

  /// ISO-8601 UTC text, matching `05`'s wire form exactly.
  ///
  /// Stored as text rather than through Drift's `dateTime()`, which persists epoch
  /// **seconds** and would silently truncate sub-second precision on a value the server
  /// will echo back. It is metadata (D-C2), but metadata that round-trips.
  final String clientCreatedAt;

  /// The request body M9 will send, as JSON text. Stored verbatim and never rewritten.
  final String payload;

  /// The `OutboxStatus.code` string, not an ordinal: reordering the enum must not
  /// reinterpret rows already sitting on a device.
  final String status;
  const OutboxRow({
    required this.sequence,
    required this.clientUuid,
    required this.operationType,
    required this.clientCreatedAt,
    required this.payload,
    required this.status,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['sequence'] = Variable<int>(sequence);
    map['client_uuid'] = Variable<String>(clientUuid);
    map['operation_type'] = Variable<String>(operationType);
    map['client_created_at'] = Variable<String>(clientCreatedAt);
    map['payload'] = Variable<String>(payload);
    map['status'] = Variable<String>(status);
    return map;
  }

  OutboxOperationsCompanion toCompanion(bool nullToAbsent) {
    return OutboxOperationsCompanion(
      sequence: Value(sequence),
      clientUuid: Value(clientUuid),
      operationType: Value(operationType),
      clientCreatedAt: Value(clientCreatedAt),
      payload: Value(payload),
      status: Value(status),
    );
  }

  factory OutboxRow.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return OutboxRow(
      sequence: serializer.fromJson<int>(json['sequence']),
      clientUuid: serializer.fromJson<String>(json['clientUuid']),
      operationType: serializer.fromJson<String>(json['operationType']),
      clientCreatedAt: serializer.fromJson<String>(json['clientCreatedAt']),
      payload: serializer.fromJson<String>(json['payload']),
      status: serializer.fromJson<String>(json['status']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'sequence': serializer.toJson<int>(sequence),
      'clientUuid': serializer.toJson<String>(clientUuid),
      'operationType': serializer.toJson<String>(operationType),
      'clientCreatedAt': serializer.toJson<String>(clientCreatedAt),
      'payload': serializer.toJson<String>(payload),
      'status': serializer.toJson<String>(status),
    };
  }

  OutboxRow copyWith({
    int? sequence,
    String? clientUuid,
    String? operationType,
    String? clientCreatedAt,
    String? payload,
    String? status,
  }) => OutboxRow(
    sequence: sequence ?? this.sequence,
    clientUuid: clientUuid ?? this.clientUuid,
    operationType: operationType ?? this.operationType,
    clientCreatedAt: clientCreatedAt ?? this.clientCreatedAt,
    payload: payload ?? this.payload,
    status: status ?? this.status,
  );
  OutboxRow copyWithCompanion(OutboxOperationsCompanion data) {
    return OutboxRow(
      sequence: data.sequence.present ? data.sequence.value : this.sequence,
      clientUuid: data.clientUuid.present
          ? data.clientUuid.value
          : this.clientUuid,
      operationType: data.operationType.present
          ? data.operationType.value
          : this.operationType,
      clientCreatedAt: data.clientCreatedAt.present
          ? data.clientCreatedAt.value
          : this.clientCreatedAt,
      payload: data.payload.present ? data.payload.value : this.payload,
      status: data.status.present ? data.status.value : this.status,
    );
  }

  @override
  String toString() {
    return (StringBuffer('OutboxRow(')
          ..write('sequence: $sequence, ')
          ..write('clientUuid: $clientUuid, ')
          ..write('operationType: $operationType, ')
          ..write('clientCreatedAt: $clientCreatedAt, ')
          ..write('payload: $payload, ')
          ..write('status: $status')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
    sequence,
    clientUuid,
    operationType,
    clientCreatedAt,
    payload,
    status,
  );
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is OutboxRow &&
          other.sequence == this.sequence &&
          other.clientUuid == this.clientUuid &&
          other.operationType == this.operationType &&
          other.clientCreatedAt == this.clientCreatedAt &&
          other.payload == this.payload &&
          other.status == this.status);
}

class OutboxOperationsCompanion extends UpdateCompanion<OutboxRow> {
  final Value<int> sequence;
  final Value<String> clientUuid;
  final Value<String> operationType;
  final Value<String> clientCreatedAt;
  final Value<String> payload;
  final Value<String> status;
  const OutboxOperationsCompanion({
    this.sequence = const Value.absent(),
    this.clientUuid = const Value.absent(),
    this.operationType = const Value.absent(),
    this.clientCreatedAt = const Value.absent(),
    this.payload = const Value.absent(),
    this.status = const Value.absent(),
  });
  OutboxOperationsCompanion.insert({
    this.sequence = const Value.absent(),
    required String clientUuid,
    required String operationType,
    required String clientCreatedAt,
    required String payload,
    required String status,
  }) : clientUuid = Value(clientUuid),
       operationType = Value(operationType),
       clientCreatedAt = Value(clientCreatedAt),
       payload = Value(payload),
       status = Value(status);
  static Insertable<OutboxRow> custom({
    Expression<int>? sequence,
    Expression<String>? clientUuid,
    Expression<String>? operationType,
    Expression<String>? clientCreatedAt,
    Expression<String>? payload,
    Expression<String>? status,
  }) {
    return RawValuesInsertable({
      if (sequence != null) 'sequence': sequence,
      if (clientUuid != null) 'client_uuid': clientUuid,
      if (operationType != null) 'operation_type': operationType,
      if (clientCreatedAt != null) 'client_created_at': clientCreatedAt,
      if (payload != null) 'payload': payload,
      if (status != null) 'status': status,
    });
  }

  OutboxOperationsCompanion copyWith({
    Value<int>? sequence,
    Value<String>? clientUuid,
    Value<String>? operationType,
    Value<String>? clientCreatedAt,
    Value<String>? payload,
    Value<String>? status,
  }) {
    return OutboxOperationsCompanion(
      sequence: sequence ?? this.sequence,
      clientUuid: clientUuid ?? this.clientUuid,
      operationType: operationType ?? this.operationType,
      clientCreatedAt: clientCreatedAt ?? this.clientCreatedAt,
      payload: payload ?? this.payload,
      status: status ?? this.status,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (sequence.present) {
      map['sequence'] = Variable<int>(sequence.value);
    }
    if (clientUuid.present) {
      map['client_uuid'] = Variable<String>(clientUuid.value);
    }
    if (operationType.present) {
      map['operation_type'] = Variable<String>(operationType.value);
    }
    if (clientCreatedAt.present) {
      map['client_created_at'] = Variable<String>(clientCreatedAt.value);
    }
    if (payload.present) {
      map['payload'] = Variable<String>(payload.value);
    }
    if (status.present) {
      map['status'] = Variable<String>(status.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('OutboxOperationsCompanion(')
          ..write('sequence: $sequence, ')
          ..write('clientUuid: $clientUuid, ')
          ..write('operationType: $operationType, ')
          ..write('clientCreatedAt: $clientCreatedAt, ')
          ..write('payload: $payload, ')
          ..write('status: $status')
          ..write(')'))
        .toString();
  }
}

class $LocalIdentitiesTable extends LocalIdentities
    with TableInfo<$LocalIdentitiesTable, LocalIdentityRow> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $LocalIdentitiesTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _idMeta = const VerificationMeta('id');
  @override
  late final GeneratedColumn<int> id = GeneratedColumn<int>(
    'id',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
    defaultValue: const Constant(1),
  );
  static const VerificationMeta _userIdMeta = const VerificationMeta('userId');
  @override
  late final GeneratedColumn<int> userId = GeneratedColumn<int>(
    'user_id',
    aliasedName,
    false,
    type: DriftSqlType.int,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _fullNameMeta = const VerificationMeta(
    'fullName',
  );
  @override
  late final GeneratedColumn<String> fullName = GeneratedColumn<String>(
    'full_name',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _rolesMeta = const VerificationMeta('roles');
  @override
  late final GeneratedColumn<String> roles = GeneratedColumn<String>(
    'roles',
    aliasedName,
    false,
    type: DriftSqlType.string,
    requiredDuringInsert: true,
  );
  static const VerificationMeta _customerIdMeta = const VerificationMeta(
    'customerId',
  );
  @override
  late final GeneratedColumn<int> customerId = GeneratedColumn<int>(
    'customer_id',
    aliasedName,
    true,
    type: DriftSqlType.int,
    requiredDuringInsert: false,
  );
  @override
  List<GeneratedColumn> get $columns => [
    id,
    userId,
    fullName,
    roles,
    customerId,
  ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'local_identity';
  @override
  VerificationContext validateIntegrity(
    Insertable<LocalIdentityRow> instance, {
    bool isInserting = false,
  }) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('id')) {
      context.handle(_idMeta, id.isAcceptableOrUnknown(data['id']!, _idMeta));
    }
    if (data.containsKey('user_id')) {
      context.handle(
        _userIdMeta,
        userId.isAcceptableOrUnknown(data['user_id']!, _userIdMeta),
      );
    } else if (isInserting) {
      context.missing(_userIdMeta);
    }
    if (data.containsKey('full_name')) {
      context.handle(
        _fullNameMeta,
        fullName.isAcceptableOrUnknown(data['full_name']!, _fullNameMeta),
      );
    } else if (isInserting) {
      context.missing(_fullNameMeta);
    }
    if (data.containsKey('roles')) {
      context.handle(
        _rolesMeta,
        roles.isAcceptableOrUnknown(data['roles']!, _rolesMeta),
      );
    } else if (isInserting) {
      context.missing(_rolesMeta);
    }
    if (data.containsKey('customer_id')) {
      context.handle(
        _customerIdMeta,
        customerId.isAcceptableOrUnknown(data['customer_id']!, _customerIdMeta),
      );
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {id};
  @override
  LocalIdentityRow map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return LocalIdentityRow(
      id: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}id'],
      )!,
      userId: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}user_id'],
      )!,
      fullName: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}full_name'],
      )!,
      roles: attachedDatabase.typeMapping.read(
        DriftSqlType.string,
        data['${effectivePrefix}roles'],
      )!,
      customerId: attachedDatabase.typeMapping.read(
        DriftSqlType.int,
        data['${effectivePrefix}customer_id'],
      ),
    );
  }

  @override
  $LocalIdentitiesTable createAlias(String alias) {
    return $LocalIdentitiesTable(attachedDatabase, alias);
  }
}

class LocalIdentityRow extends DataClass
    implements Insertable<LocalIdentityRow> {
  /// **Always 1.** One device, one signed-in user; a second row would make "which identity?"
  /// a question every reader has to answer.
  final int id;
  final int userId;
  final String fullName;

  /// A JSON array of `Role.code` strings — `["SALESMAN","DELIVERY"]`.
  ///
  /// **An array, because P-7 and `05` C-12 say roles are an array.** Flattening to a single
  /// "primary role" here would reintroduce, in storage, the exact bug the tab bar was
  /// written to avoid. Codes rather than enum indices: reordering the Dart enum must not
  /// silently reinterpret a row already sitting on a device (the same reasoning as
  /// `outbox_operation.status`).
  final String roles;

  /// The shop a `RETAILER` *is* (`05` AD-11). Null for internal staff.
  final int? customerId;
  const LocalIdentityRow({
    required this.id,
    required this.userId,
    required this.fullName,
    required this.roles,
    this.customerId,
  });
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['id'] = Variable<int>(id);
    map['user_id'] = Variable<int>(userId);
    map['full_name'] = Variable<String>(fullName);
    map['roles'] = Variable<String>(roles);
    if (!nullToAbsent || customerId != null) {
      map['customer_id'] = Variable<int>(customerId);
    }
    return map;
  }

  LocalIdentitiesCompanion toCompanion(bool nullToAbsent) {
    return LocalIdentitiesCompanion(
      id: Value(id),
      userId: Value(userId),
      fullName: Value(fullName),
      roles: Value(roles),
      customerId: customerId == null && nullToAbsent
          ? const Value.absent()
          : Value(customerId),
    );
  }

  factory LocalIdentityRow.fromJson(
    Map<String, dynamic> json, {
    ValueSerializer? serializer,
  }) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return LocalIdentityRow(
      id: serializer.fromJson<int>(json['id']),
      userId: serializer.fromJson<int>(json['userId']),
      fullName: serializer.fromJson<String>(json['fullName']),
      roles: serializer.fromJson<String>(json['roles']),
      customerId: serializer.fromJson<int?>(json['customerId']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'id': serializer.toJson<int>(id),
      'userId': serializer.toJson<int>(userId),
      'fullName': serializer.toJson<String>(fullName),
      'roles': serializer.toJson<String>(roles),
      'customerId': serializer.toJson<int?>(customerId),
    };
  }

  LocalIdentityRow copyWith({
    int? id,
    int? userId,
    String? fullName,
    String? roles,
    Value<int?> customerId = const Value.absent(),
  }) => LocalIdentityRow(
    id: id ?? this.id,
    userId: userId ?? this.userId,
    fullName: fullName ?? this.fullName,
    roles: roles ?? this.roles,
    customerId: customerId.present ? customerId.value : this.customerId,
  );
  LocalIdentityRow copyWithCompanion(LocalIdentitiesCompanion data) {
    return LocalIdentityRow(
      id: data.id.present ? data.id.value : this.id,
      userId: data.userId.present ? data.userId.value : this.userId,
      fullName: data.fullName.present ? data.fullName.value : this.fullName,
      roles: data.roles.present ? data.roles.value : this.roles,
      customerId: data.customerId.present
          ? data.customerId.value
          : this.customerId,
    );
  }

  @override
  String toString() {
    return (StringBuffer('LocalIdentityRow(')
          ..write('id: $id, ')
          ..write('userId: $userId, ')
          ..write('fullName: $fullName, ')
          ..write('roles: $roles, ')
          ..write('customerId: $customerId')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(id, userId, fullName, roles, customerId);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is LocalIdentityRow &&
          other.id == this.id &&
          other.userId == this.userId &&
          other.fullName == this.fullName &&
          other.roles == this.roles &&
          other.customerId == this.customerId);
}

class LocalIdentitiesCompanion extends UpdateCompanion<LocalIdentityRow> {
  final Value<int> id;
  final Value<int> userId;
  final Value<String> fullName;
  final Value<String> roles;
  final Value<int?> customerId;
  const LocalIdentitiesCompanion({
    this.id = const Value.absent(),
    this.userId = const Value.absent(),
    this.fullName = const Value.absent(),
    this.roles = const Value.absent(),
    this.customerId = const Value.absent(),
  });
  LocalIdentitiesCompanion.insert({
    this.id = const Value.absent(),
    required int userId,
    required String fullName,
    required String roles,
    this.customerId = const Value.absent(),
  }) : userId = Value(userId),
       fullName = Value(fullName),
       roles = Value(roles);
  static Insertable<LocalIdentityRow> custom({
    Expression<int>? id,
    Expression<int>? userId,
    Expression<String>? fullName,
    Expression<String>? roles,
    Expression<int>? customerId,
  }) {
    return RawValuesInsertable({
      if (id != null) 'id': id,
      if (userId != null) 'user_id': userId,
      if (fullName != null) 'full_name': fullName,
      if (roles != null) 'roles': roles,
      if (customerId != null) 'customer_id': customerId,
    });
  }

  LocalIdentitiesCompanion copyWith({
    Value<int>? id,
    Value<int>? userId,
    Value<String>? fullName,
    Value<String>? roles,
    Value<int?>? customerId,
  }) {
    return LocalIdentitiesCompanion(
      id: id ?? this.id,
      userId: userId ?? this.userId,
      fullName: fullName ?? this.fullName,
      roles: roles ?? this.roles,
      customerId: customerId ?? this.customerId,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (id.present) {
      map['id'] = Variable<int>(id.value);
    }
    if (userId.present) {
      map['user_id'] = Variable<int>(userId.value);
    }
    if (fullName.present) {
      map['full_name'] = Variable<String>(fullName.value);
    }
    if (roles.present) {
      map['roles'] = Variable<String>(roles.value);
    }
    if (customerId.present) {
      map['customer_id'] = Variable<int>(customerId.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('LocalIdentitiesCompanion(')
          ..write('id: $id, ')
          ..write('userId: $userId, ')
          ..write('fullName: $fullName, ')
          ..write('roles: $roles, ')
          ..write('customerId: $customerId')
          ..write(')'))
        .toString();
  }
}

abstract class _$AppDatabase extends GeneratedDatabase {
  _$AppDatabase(QueryExecutor e) : super(e);
  $AppDatabaseManager get managers => $AppDatabaseManager(this);
  late final $OutboxOperationsTable outboxOperations = $OutboxOperationsTable(
    this,
  );
  late final $LocalIdentitiesTable localIdentities = $LocalIdentitiesTable(
    this,
  );
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities => [
    outboxOperations,
    localIdentities,
  ];
}

typedef $$OutboxOperationsTableCreateCompanionBuilder =
    OutboxOperationsCompanion Function({
      Value<int> sequence,
      required String clientUuid,
      required String operationType,
      required String clientCreatedAt,
      required String payload,
      required String status,
    });
typedef $$OutboxOperationsTableUpdateCompanionBuilder =
    OutboxOperationsCompanion Function({
      Value<int> sequence,
      Value<String> clientUuid,
      Value<String> operationType,
      Value<String> clientCreatedAt,
      Value<String> payload,
      Value<String> status,
    });

class $$OutboxOperationsTableFilterComposer
    extends Composer<_$AppDatabase, $OutboxOperationsTable> {
  $$OutboxOperationsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<int> get sequence => $composableBuilder(
    column: $table.sequence,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get clientUuid => $composableBuilder(
    column: $table.clientUuid,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get operationType => $composableBuilder(
    column: $table.operationType,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get clientCreatedAt => $composableBuilder(
    column: $table.clientCreatedAt,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get payload => $composableBuilder(
    column: $table.payload,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get status => $composableBuilder(
    column: $table.status,
    builder: (column) => ColumnFilters(column),
  );
}

class $$OutboxOperationsTableOrderingComposer
    extends Composer<_$AppDatabase, $OutboxOperationsTable> {
  $$OutboxOperationsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<int> get sequence => $composableBuilder(
    column: $table.sequence,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get clientUuid => $composableBuilder(
    column: $table.clientUuid,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get operationType => $composableBuilder(
    column: $table.operationType,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get clientCreatedAt => $composableBuilder(
    column: $table.clientCreatedAt,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get payload => $composableBuilder(
    column: $table.payload,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get status => $composableBuilder(
    column: $table.status,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$OutboxOperationsTableAnnotationComposer
    extends Composer<_$AppDatabase, $OutboxOperationsTable> {
  $$OutboxOperationsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<int> get sequence =>
      $composableBuilder(column: $table.sequence, builder: (column) => column);

  GeneratedColumn<String> get clientUuid => $composableBuilder(
    column: $table.clientUuid,
    builder: (column) => column,
  );

  GeneratedColumn<String> get operationType => $composableBuilder(
    column: $table.operationType,
    builder: (column) => column,
  );

  GeneratedColumn<String> get clientCreatedAt => $composableBuilder(
    column: $table.clientCreatedAt,
    builder: (column) => column,
  );

  GeneratedColumn<String> get payload =>
      $composableBuilder(column: $table.payload, builder: (column) => column);

  GeneratedColumn<String> get status =>
      $composableBuilder(column: $table.status, builder: (column) => column);
}

class $$OutboxOperationsTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $OutboxOperationsTable,
          OutboxRow,
          $$OutboxOperationsTableFilterComposer,
          $$OutboxOperationsTableOrderingComposer,
          $$OutboxOperationsTableAnnotationComposer,
          $$OutboxOperationsTableCreateCompanionBuilder,
          $$OutboxOperationsTableUpdateCompanionBuilder,
          (
            OutboxRow,
            BaseReferences<_$AppDatabase, $OutboxOperationsTable, OutboxRow>,
          ),
          OutboxRow,
          PrefetchHooks Function()
        > {
  $$OutboxOperationsTableTableManager(
    _$AppDatabase db,
    $OutboxOperationsTable table,
  ) : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$OutboxOperationsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$OutboxOperationsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$OutboxOperationsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<int> sequence = const Value.absent(),
                Value<String> clientUuid = const Value.absent(),
                Value<String> operationType = const Value.absent(),
                Value<String> clientCreatedAt = const Value.absent(),
                Value<String> payload = const Value.absent(),
                Value<String> status = const Value.absent(),
              }) => OutboxOperationsCompanion(
                sequence: sequence,
                clientUuid: clientUuid,
                operationType: operationType,
                clientCreatedAt: clientCreatedAt,
                payload: payload,
                status: status,
              ),
          createCompanionCallback:
              ({
                Value<int> sequence = const Value.absent(),
                required String clientUuid,
                required String operationType,
                required String clientCreatedAt,
                required String payload,
                required String status,
              }) => OutboxOperationsCompanion.insert(
                sequence: sequence,
                clientUuid: clientUuid,
                operationType: operationType,
                clientCreatedAt: clientCreatedAt,
                payload: payload,
                status: status,
              ),
          withReferenceMapper: (p0) => p0
              .map((e) => (e.readTable(table), BaseReferences(db, table, e)))
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$OutboxOperationsTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $OutboxOperationsTable,
      OutboxRow,
      $$OutboxOperationsTableFilterComposer,
      $$OutboxOperationsTableOrderingComposer,
      $$OutboxOperationsTableAnnotationComposer,
      $$OutboxOperationsTableCreateCompanionBuilder,
      $$OutboxOperationsTableUpdateCompanionBuilder,
      (
        OutboxRow,
        BaseReferences<_$AppDatabase, $OutboxOperationsTable, OutboxRow>,
      ),
      OutboxRow,
      PrefetchHooks Function()
    >;
typedef $$LocalIdentitiesTableCreateCompanionBuilder =
    LocalIdentitiesCompanion Function({
      Value<int> id,
      required int userId,
      required String fullName,
      required String roles,
      Value<int?> customerId,
    });
typedef $$LocalIdentitiesTableUpdateCompanionBuilder =
    LocalIdentitiesCompanion Function({
      Value<int> id,
      Value<int> userId,
      Value<String> fullName,
      Value<String> roles,
      Value<int?> customerId,
    });

class $$LocalIdentitiesTableFilterComposer
    extends Composer<_$AppDatabase, $LocalIdentitiesTable> {
  $$LocalIdentitiesTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<int> get userId => $composableBuilder(
    column: $table.userId,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get fullName => $composableBuilder(
    column: $table.fullName,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<String> get roles => $composableBuilder(
    column: $table.roles,
    builder: (column) => ColumnFilters(column),
  );

  ColumnFilters<int> get customerId => $composableBuilder(
    column: $table.customerId,
    builder: (column) => ColumnFilters(column),
  );
}

class $$LocalIdentitiesTableOrderingComposer
    extends Composer<_$AppDatabase, $LocalIdentitiesTable> {
  $$LocalIdentitiesTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<int> get id => $composableBuilder(
    column: $table.id,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<int> get userId => $composableBuilder(
    column: $table.userId,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get fullName => $composableBuilder(
    column: $table.fullName,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<String> get roles => $composableBuilder(
    column: $table.roles,
    builder: (column) => ColumnOrderings(column),
  );

  ColumnOrderings<int> get customerId => $composableBuilder(
    column: $table.customerId,
    builder: (column) => ColumnOrderings(column),
  );
}

class $$LocalIdentitiesTableAnnotationComposer
    extends Composer<_$AppDatabase, $LocalIdentitiesTable> {
  $$LocalIdentitiesTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<int> get id =>
      $composableBuilder(column: $table.id, builder: (column) => column);

  GeneratedColumn<int> get userId =>
      $composableBuilder(column: $table.userId, builder: (column) => column);

  GeneratedColumn<String> get fullName =>
      $composableBuilder(column: $table.fullName, builder: (column) => column);

  GeneratedColumn<String> get roles =>
      $composableBuilder(column: $table.roles, builder: (column) => column);

  GeneratedColumn<int> get customerId => $composableBuilder(
    column: $table.customerId,
    builder: (column) => column,
  );
}

class $$LocalIdentitiesTableTableManager
    extends
        RootTableManager<
          _$AppDatabase,
          $LocalIdentitiesTable,
          LocalIdentityRow,
          $$LocalIdentitiesTableFilterComposer,
          $$LocalIdentitiesTableOrderingComposer,
          $$LocalIdentitiesTableAnnotationComposer,
          $$LocalIdentitiesTableCreateCompanionBuilder,
          $$LocalIdentitiesTableUpdateCompanionBuilder,
          (
            LocalIdentityRow,
            BaseReferences<
              _$AppDatabase,
              $LocalIdentitiesTable,
              LocalIdentityRow
            >,
          ),
          LocalIdentityRow,
          PrefetchHooks Function()
        > {
  $$LocalIdentitiesTableTableManager(
    _$AppDatabase db,
    $LocalIdentitiesTable table,
  ) : super(
        TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$LocalIdentitiesTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$LocalIdentitiesTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$LocalIdentitiesTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                Value<int> userId = const Value.absent(),
                Value<String> fullName = const Value.absent(),
                Value<String> roles = const Value.absent(),
                Value<int?> customerId = const Value.absent(),
              }) => LocalIdentitiesCompanion(
                id: id,
                userId: userId,
                fullName: fullName,
                roles: roles,
                customerId: customerId,
              ),
          createCompanionCallback:
              ({
                Value<int> id = const Value.absent(),
                required int userId,
                required String fullName,
                required String roles,
                Value<int?> customerId = const Value.absent(),
              }) => LocalIdentitiesCompanion.insert(
                id: id,
                userId: userId,
                fullName: fullName,
                roles: roles,
                customerId: customerId,
              ),
          withReferenceMapper: (p0) => p0
              .map((e) => (e.readTable(table), BaseReferences(db, table, e)))
              .toList(),
          prefetchHooksCallback: null,
        ),
      );
}

typedef $$LocalIdentitiesTableProcessedTableManager =
    ProcessedTableManager<
      _$AppDatabase,
      $LocalIdentitiesTable,
      LocalIdentityRow,
      $$LocalIdentitiesTableFilterComposer,
      $$LocalIdentitiesTableOrderingComposer,
      $$LocalIdentitiesTableAnnotationComposer,
      $$LocalIdentitiesTableCreateCompanionBuilder,
      $$LocalIdentitiesTableUpdateCompanionBuilder,
      (
        LocalIdentityRow,
        BaseReferences<_$AppDatabase, $LocalIdentitiesTable, LocalIdentityRow>,
      ),
      LocalIdentityRow,
      PrefetchHooks Function()
    >;

class $AppDatabaseManager {
  final _$AppDatabase _db;
  $AppDatabaseManager(this._db);
  $$OutboxOperationsTableTableManager get outboxOperations =>
      $$OutboxOperationsTableTableManager(_db, _db.outboxOperations);
  $$LocalIdentitiesTableTableManager get localIdentities =>
      $$LocalIdentitiesTableTableManager(_db, _db.localIdentities);
}
