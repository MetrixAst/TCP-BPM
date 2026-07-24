import 'package:flutter/material.dart';

class MetrixRadius {
  MetrixRadius._();
  static const md = 12.0; // --bpm-radius
  static const sm = 8.0;  // --bpm-radius-sm
}

class MetrixShadows {
  MetrixShadows._();
  // --bpm-shadow: 0 1px 3px rgba(17, 26, 53, 0.08)
  static const card = [
    BoxShadow(
      color: Color(0x14111A35), // rgba(17,26,53,0.08) ≈ alpha 0x14
      offset: Offset(0, 1),
      blurRadius: 3,
    ),
  ];
}