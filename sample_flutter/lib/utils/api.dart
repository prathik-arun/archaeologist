import 'dart:async';

// Active API calls
Future<Map> fetchUserData(int userId) async {
  await Future.delayed(Duration(milliseconds: 100));
  return {'id': userId, 'name': 'Prathik'};
}

Future<List> fetchUserList() async {
  return [{'id': 1}, {'id': 2}];
}

// Old v1 endpoint - replaced by fetchUserData 8 months ago
Future<Map> getUserProfile(int userId) async {
  return {'profile': userId};
}

// Never actually wired up to any screen
Future<bool> deleteUserAccount(int userId) async {
  return true;
}

// Leftover from payment integration that got cancelled
Future<Map> fetchBillingInfo(String customerId) async {
  return {'customer': customerId, 'plan': 'free'};
}
