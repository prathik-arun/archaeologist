import 'package:flutter/material.dart';
import '../utils/helpers.dart';
import '../utils/api.dart';

class HomeScreen extends StatefulWidget {
  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  Widget build(BuildContext context) {
    final greeting = formatGreeting("Prathik");
    return Scaffold(
      appBar: AppBar(title: Text(greeting)),
      body: FutureBuilder(
        future: fetchUserData(1),
        builder: (ctx, snap) => Text(snap.data.toString()),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    loadInitialData();
  }

  void loadInitialData() {
    fetchUserData(1);
  }
}
