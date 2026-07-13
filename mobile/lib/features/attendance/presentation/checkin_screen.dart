import 'dart:io';

import 'package:flutter/material.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../data/attendance_repository.dart';
import '../data/checkin_capture_service.dart';
import '../data/checkin_event_type.dart';

class CheckinScreen extends StatefulWidget {
  const CheckinScreen({super.key});

  @override
  State<CheckinScreen> createState() => _CheckinScreenState();
}

class _CheckinScreenState extends State<CheckinScreen> {
  late final AttendanceRepository _repository;
  final CheckinCaptureService _captureService = CheckinCaptureService();

  CheckinEventType _selectedType = CheckinEventType.dayStart;
  File? _capturedPhoto;
  double? _latitude;
  double? _longitude;

  bool _isCapturing = false;
  bool _isSubmitting = false;
  String? _errorMessage;
  String? _successMessage;

  @override
  void initState() {
    super.initState();
    _repository = AttendanceRepository(dio: DioClient().dio);
  }

  Future<void> _handleCapture() async {
    setState(() {
      _isCapturing = true;
      _errorMessage = null;
      _successMessage = null;
    });

    final result = await _captureService.capture();

    if (!mounted) return;

    setState(() {
      _isCapturing = false;
      switch (result) {
        case CaptureSuccess(:final photo, :final latitude, :final longitude):
          _capturedPhoto = photo;
          _latitude = latitude;
          _longitude = longitude;
        case CaptureFailure(:final message):
          _errorMessage = message;
      }
    });
  }

  Future<void> _handleSubmit() async {
    final photo = _capturedPhoto;
    if (photo == null) {
      setState(() => _errorMessage = 'Сначала сделайте фото');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
      _successMessage = null;
    });

    final result = await _repository.checkin(
      eventType: _selectedType.value,
      photo: photo,
      latitude: _latitude,
      longitude: _longitude,
    );

    if (!mounted) return;

    setState(() {
      _isSubmitting = false;
      switch (result) {
        case Success():
          _successMessage = 'Отметка сохранена';
          _capturedPhoto = null;
          _latitude = null;
          _longitude = null;
        case Failure(:final message):
          _errorMessage = message;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Чек-ин')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            DropdownButtonFormField<CheckinEventType>(
              initialValue: _selectedType,
              decoration: const InputDecoration(labelText: 'Тип отметки'),
              items: CheckinEventType.values
                  .map((type) => DropdownMenuItem(
                value: type,
                child: Text(type.label),
              ))
                  .toList(),
              onChanged: (value) {
                if (value != null) setState(() => _selectedType = value);
              },
            ),
            const SizedBox(height: 24),
            if (_capturedPhoto != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.file(_capturedPhoto!, height: 240, fit: BoxFit.cover),
              )
            else
              Container(
                height: 240,
                decoration: BoxDecoration(
                  color: Colors.grey.shade200,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Center(
                  child: Icon(Icons.camera_alt_outlined, size: 48, color: Colors.grey),
                ),
              ),
            const SizedBox(height: 12),
            if (_latitude != null && _longitude != null)
              Text(
                'Координаты: ${_latitude!.toStringAsFixed(5)}, ${_longitude!.toStringAsFixed(5)}',
                style: Theme.of(context).textTheme.bodySmall,
                textAlign: TextAlign.center,
              )
            else if (_capturedPhoto != null)
              Text(
                'Геолокация недоступна',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.orange),
                textAlign: TextAlign.center,
              ),
            const SizedBox(height: 24),
            OutlinedButton.icon(
              onPressed: _isCapturing ? null : _handleCapture,
              icon: _isCapturing
                  ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
                  : const Icon(Icons.camera_alt),
              label: Text(_capturedPhoto == null ? 'Сделать фото' : 'Переснять'),
            ),
            const SizedBox(height: 16),
            if (_errorMessage != null)
              Text(
                _errorMessage!,
                style: const TextStyle(color: Colors.red),
                textAlign: TextAlign.center,
              ),
            if (_successMessage != null)
              Text(
                _successMessage!,
                style: const TextStyle(color: Colors.green),
                textAlign: TextAlign.center,
              ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: (_isSubmitting || _capturedPhoto == null) ? null : _handleSubmit,
              child: _isSubmitting
                  ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
                  : const Text('Отправить отметку'),
            ),
          ],
        ),
      ),
    );
  }
}