import 'package:app/config/runtime_config.dart';
import 'package:app/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('renders the empty application marker', (tester) async {
    await tester.pumpWidget(const TemplateApp());

    expect(find.text('Application'), findsOneWidget);
  });

  test('uses same-origin defaults', () {
    expect(RuntimeConfig.apiBaseUrl, '/api/');
    expect(RuntimeConfig.natsWebSocketUrl, '/nats/');
  });
}
