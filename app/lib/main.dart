import 'package:flutter/material.dart';

void main() {
  runApp(const TemplateApp());
}

class TemplateApp extends StatelessWidget {
  const TemplateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Application',
      home: Scaffold(
        appBar: AppBar(title: const Text('Application')),
        body: const Center(
          child: Text('This application is ready for integration.'),
        ),
      ),
    );
  }
}
