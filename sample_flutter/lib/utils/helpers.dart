// Active helpers
String formatGreeting(String name) {
  return 'Hello, $name!';
}

String formatDate(DateTime date) {
  return '${date.day}/${date.month}/${date.year}';
}

// Old experiment that never shipped - Q1 2023
String formatLegacyUsername(String email) {
  return email.split('@').first.replaceAll('.', '_');
}

// Was used in v1 onboarding flow, removed 10 months ago
String generateWelcomeMessage(String name, String plan) {
  return 'Welcome to $plan, $name! Get started below.';
}

// Leftover from old analytics integration
Map<String, dynamic> buildAnalyticsPayload(String event, Map data) {
  return {'event': event, 'data': data, 'ts': DateTime.now().millisecondsSinceEpoch};
}

// Utility nobody calls anymore
double calculateDiscountedPrice(double price, double discountPercent) {
  return price * (1 - discountPercent / 100);
}
