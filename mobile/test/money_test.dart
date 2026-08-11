// P-3 / `05` AD-02 / C-1. The whole point of this type is what it REFUSES.
import 'package:districore/core/money.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Money.fromJson', () {
    test('parses a decimal string exactly, keeping its scale', () {
      expect(Money.fromJson('11800.00').toJson(), '11800.00');
      expect(Money.fromJson('0.001').toJson(), '0.001');
      expect(Money.fromJson('-12.50').toJson(), '-12.50');
    });

    test('REFUSES a JSON number — the defect this type exists for', () {
      // `jsonDecode` produces `double` for any unquoted number. Converting it would store
      // a value we already know is wrong; throwing makes TD-36 visible instead of silent.
      expect(() => Money.fromJson(1180.0), throwsA(isA<MoneyFormatException>()));
      expect(() => Money.fromJson(1180), throwsA(isA<MoneyFormatException>()));
    });

    test('refuses null and non-numeric text rather than defaulting to zero', () {
      expect(() => Money.fromJson(null), throwsA(isA<MoneyFormatException>()));
      expect(() => Money.fromJson('twelve'), throwsA(isA<MoneyFormatException>()));
      expect(() => Money.fromJson(''), throwsA(isA<MoneyFormatException>()));
    });

    test('the refusal message names the contract, not just the type', () {
      try {
        Money.fromJson(0.1);
        fail('expected a refusal');
      } on MoneyFormatException catch (e) {
        expect(e.message, contains('AD-02'));
      }
    });
  });

  group('arithmetic is exact', () {
    test('0.1 + 0.2 == 0.3, which is the reason none of this is a double', () {
      final sum = Money.parse('0.1') + Money.parse('0.2');
      expect(sum, Money.parse('0.3'));
      expect(sum.toJson(), '0.3');
    });

    test('a long chain of paise does not drift', () {
      var total = Money.zero;
      for (var i = 0; i < 1000; i++) {
        total = total + Money.parse('0.01');
      }
      expect(total, Money.parse('10.00'));
    });
  });

  group('presentation', () {
    test('scale is chosen by the caller — 14,2 money, 14,3 quantity (05)', () {
      expect(Money.parse('1180').toStringAsScale(2), '1180.00');
      expect(Money.parse('24').toStringAsScale(3), '24.000');
    });

    test('round-trips through the wire form unchanged', () {
      const wire = '99999.99';
      expect(Money.fromJson(wire).toJson(), wire);
    });
  });
}
