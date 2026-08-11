// `05` C-10 / FR-IAM-009. device_id travels in the BODY — every example in `05` §9 and
// every DRF serializer reads it from `request.data`. A header would be silently ignored.
import 'package:dio/dio.dart';
import 'package:districore/data/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

({ApiClient client, FakeAdapter adapter}) build() {
  final adapter = FakeAdapter((options, _) async => jsonBody(200, {'ok': true}));
  final dio = Dio()..httpClientAdapter = adapter;
  final client = ApiClient(
    baseUrl: 'https://api.test',
    tokens: FakeTokens(),
    dio: dio,
    refreshDio: Dio()..httpClientAdapter = adapter,
  );
  return (client: client, adapter: adapter);
}

void main() {
  test('a write carries device_id in the body, not in a header', () async {
    final env = build();
    await env.client.post<Object?>('/visits', body: <String, dynamic>{'customer_id': 4},
        decode: (b) => b);
    final sent = env.adapter.requests.single;
    expect(sent.body['device_id'], 'device-abc');
    expect(sent.headers.containsKey('device_id'), isFalse,
        reason: 'the server reads request.data; a header would be dropped silently');
  });

  test('a read is left alone — C-10 says every WRITE', () async {
    final env = build();
    await env.client.get<Object?>('/deliveries', decode: (b) => b);
    expect(env.adapter.requests.single.data, isNull);
  });

  test('an existing device_id is preserved', () async {
    // A queued outbox row records the device that CAPTURED the operation, which may not be
    // the device that eventually sends it.
    final env = build();
    await env.client.post<Object?>('/visits',
        body: <String, dynamic>{'device_id': 'captured-on-another-phone'}, decode: (b) => b);
    expect(env.adapter.requests.single.body['device_id'], 'captured-on-another-phone');
  });

  test('the caller\'s map is not mutated', () async {
    final env = build();
    final body = <String, dynamic>{'customer_id': 4};
    await env.client.post<Object?>('/visits', body: body, decode: (b) => b);
    expect(body.containsKey('device_id'), isFalse,
        reason: 'mutating it would edit the outbox row the body came from');
  });
}
