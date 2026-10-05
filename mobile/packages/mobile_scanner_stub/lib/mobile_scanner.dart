import 'package:flutter/material.dart';

class Barcode {
  const Barcode({this.rawValue});
  final String? rawValue;
}

class BarcodeCapture {
  const BarcodeCapture({this.barcodes = const []});
  final List<Barcode> barcodes;
}

class MobileScannerController {
  Future<void> toggleTorch() async {}
  void dispose() {}
}

class MobileScanner extends StatelessWidget {
  const MobileScanner({super.key, this.controller, this.onDetect});

  final MobileScannerController? controller;
  final void Function(BarcodeCapture capture)? onDetect;

  @override
  Widget build(BuildContext context) => const ColoredBox(color: Colors.black);
}
