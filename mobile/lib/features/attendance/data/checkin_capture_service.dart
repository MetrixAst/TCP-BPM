import 'dart:io';

import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';

sealed class CaptureResult {
  const CaptureResult();
}

class CaptureSuccess extends CaptureResult {
  final File photo;
  final double? latitude;
  final double? longitude;
  const CaptureSuccess({required this.photo, this.latitude, this.longitude});
}

class CaptureFailure extends CaptureResult {
  final String message;
  const CaptureFailure(this.message);
}

class CheckinCaptureService {
  final ImagePicker _picker = ImagePicker();

  Future<CaptureResult> capture() async {
    final photoResult = await _takePhoto();
    if (photoResult == null) {
      return const CaptureFailure('Съёмка отменена');
    }

    final position = await _getPosition();

    return CaptureSuccess(
      photo: photoResult,
      latitude: position?.latitude,
      longitude: position?.longitude,
    );
  }

  Future<File?> _takePhoto() async {
    try {
      final xFile = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 80,
      );
      if (xFile == null) return null;
      return File(xFile.path);
    } catch (_) {
      return null;
    }
  }

  Future<Position?> _getPosition() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return null;

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }

      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      );
    } catch (_) {
      return null;
    }
  }
}