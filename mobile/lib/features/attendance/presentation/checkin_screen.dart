import 'dart:io';

import 'package:flutter/material.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../data/attendance_repository.dart';
import '../data/checkin_capture_service.dart';
import '../data/checkin_event_type.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';

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
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Чек-ин'),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Тип отметки', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: MetrixColors.textMuted)),
                  const SizedBox(height: AppSpacing.xs),
                  DropdownButtonFormField<CheckinEventType>(
                    initialValue: _selectedType,
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: MetrixColors.surfaceMuted,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: const BorderSide(color: MetrixColors.border),
                      ),
                    ),
                    items: CheckinEventType.values
                        .map((type) => DropdownMenuItem(value: type, child: Text(type.label)))
                        .toList(),
                    onChanged: (value) {
                      if (value != null) setState(() => _selectedType = value);
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            AppCard(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: _capturedPhoto != null
                        ? Image.file(_capturedPhoto!, height: 220, width: double.infinity, fit: BoxFit.cover)
                        : Container(
                      height: 220,
                      width: double.infinity,
                      color: MetrixColors.surfaceMuted,
                      child: const Icon(Icons.camera_alt_outlined, size: 44, color: MetrixColors.textMuted),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  if (_latitude != null && _longitude != null)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.location_on, size: 16, color: MetrixColors.accent),
                        const SizedBox(width: 4),
                        Text(
                          '${_latitude!.toStringAsFixed(5)}, ${_longitude!.toStringAsFixed(5)}',
                          style: const TextStyle(fontSize: 12, color: MetrixColors.textMuted),
                        ),
                      ],
                    )
                  else if (_capturedPhoto != null)
                    const Text('Геолокация недоступна', style: TextStyle(fontSize: 12, color: MetrixColors.warning)),
                  const SizedBox(height: AppSpacing.sm),
                  AppButton(
                    label: _capturedPhoto == null ? 'Сделать фото' : 'Переснять',
                    variant: AppButtonVariant.secondary,
                    icon: Icons.camera_alt,
                    isLoading: _isCapturing,
                    onPressed: _handleCapture,
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            if (_errorMessage != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(_errorMessage!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
              ),
            if (_successMessage != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(_successMessage!, style: const TextStyle(color: MetrixColors.accent), textAlign: TextAlign.center),
              ),
            AppButton(
              label: 'Отправить отметку',
              isLoading: _isSubmitting,
              onPressed: _capturedPhoto == null ? null : _handleSubmit,
            ),
          ],
        ),
      ),
    );
  }
}