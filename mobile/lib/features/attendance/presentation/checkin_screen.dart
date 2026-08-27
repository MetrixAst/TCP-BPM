import 'dart:io';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

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
import 'package:connectivity_plus/connectivity_plus.dart';
import '../../../core/database/app_database.dart';
import '../../../core/database/outbox_repository.dart';

enum _CheckinMode { face, qr }

class CheckinScreen extends StatefulWidget {
  const CheckinScreen({super.key});

  @override
  State<CheckinScreen> createState() => _CheckinScreenState();
}

class _CheckinScreenState extends State<CheckinScreen> {
  late final AttendanceRepository _repository;
  late final OutboxRepository _outboxRepo;
  final CheckinCaptureService _captureService = CheckinCaptureService();

  _CheckinMode _mode = _CheckinMode.face;
  CheckinEventType? _selectedType;
  File? _capturedPhoto;
  double? _latitude;
  double? _longitude;

  bool _isCapturing = false;
  bool _isSubmitting = false;
  bool _isLoadingStatus = true;
  String? _errorMessage;
  String? _successMessage;

  Set<CheckinEventType> _completedTypes = {};

  @override
  void initState() {
    super.initState();
    _repository = AttendanceRepository(dio: DioClient().dio);
    _loadTodayStatus();
    _outboxRepo = OutboxRepository(db: AppDatabase.instance);
  }

  Future<void> _loadTodayStatus() async {
    setState(() => _isLoadingStatus = true);

    final result = await _repository.getToday();

    if (!mounted) return;

    setState(() {
      _isLoadingStatus = false;
      switch (result) {
        case Success(:final data):
          _completedTypes = data.where((s) => s.isCompleted).map((s) => s.type).toSet();
          // выбираем первый ещё не отмеченный тип по умолчанию
          final available = CheckinEventType.values.where((t) => !_completedTypes.contains(t));
          _selectedType = available.isNotEmpty ? available.first : null;
        case Failure():
          // если не удалось загрузить статус — не блокируем чек-ин, просто не дизейблим ничего
          _selectedType = CheckinEventType.dayStart;
      }
    });
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
    final type = _selectedType;
    if (photo == null || type == null) {
      setState(() => _errorMessage = 'Сначала сделайте фото');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
      _successMessage = null;
    });

    final connectivity = await Connectivity().checkConnectivity();
    final isOffline = connectivity.every((r) => r == ConnectivityResult.none);

    if (isOffline) {
      await _outboxRepo.enqueue(
        type: OutboxOperationType.checkin,
        payload: {
          'event_type': type.value,
          'latitude': _latitude,
          'longitude': _longitude,
        },
        filePath: photo.path,
      );

      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _successMessage = 'Нет сети — отметка сохранена и будет отправлена позже';
        _capturedPhoto = null;
        _latitude = null;
        _longitude = null;
        _completedTypes = {..._completedTypes, type};
        final available = CheckinEventType.values.where((t) => !_completedTypes.contains(t));
        _selectedType = available.isNotEmpty ? available.first : null;
      });
      return;
    }

    final result = await _repository.checkin(
      eventType: type.value,
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
          _completedTypes = {..._completedTypes, type};
          final available = CheckinEventType.values.where((t) => !_completedTypes.contains(t));
          _selectedType = available.isNotEmpty ? available.first : null;
        case Failure(:final message):
          _errorMessage = message;
      }
    });
  }

  Future<void> _handleScanQr() async {
    final type = _selectedType;
    if (type == null) {
      setState(() => _errorMessage = 'Выберите тип отметки');
      return;
    }

    final token = await context.push<String>('/qr-scanner');
    if (token == null || !mounted) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
      _successMessage = null;
    });

    final connectivity = await Connectivity().checkConnectivity();
    final isOffline = connectivity.every((r) => r == ConnectivityResult.none);

    // QR-токен короткоживущий: если сохранить попытку в offline-очередь и
    // отправить её позже, к моменту доставки токен почти наверняка истечёт,
    // а сотруднику уже показали бы "успех". Поэтому в офлайне сразу ошибка,
    // без записи в OutboxRepository (в отличие от Face-чекина).
    if (isOffline) {
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _errorMessage = 'Нет сети. Отсканируйте QR ещё раз, когда появится соединение.';
      });
      return;
    }

    final result = await _repository.checkinQr(
      eventType: type.value,
      token: token,
      latitude: _latitude,
      longitude: _longitude,
      idempotencyKey: const Uuid().v4(),
    );

    if (!mounted) return;

    setState(() {
      _isSubmitting = false;
      switch (result) {
        case Success():
          _successMessage = 'Отметка сохранена';
          _completedTypes = {..._completedTypes, type};
          final available = CheckinEventType.values.where((t) => !_completedTypes.contains(t));
          _selectedType = available.isNotEmpty ? available.first : null;
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
      body: _isLoadingStatus
          ? const Center(child: CircularProgressIndicator())
          : _buildBody(),
    );
  }

  Widget _buildBody() {
    final allDone = _selectedType == null && _completedTypes.length == CheckinEventType.values.length;
    if (allDone) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.check_circle_rounded, size: 48, color: MetrixColors.accent),
              SizedBox(height: AppSpacing.sm),
              Text(
                'Все отметки на сегодня сделаны',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SegmentedButton<_CheckinMode>(
            segments: const [
              ButtonSegment(
                value: _CheckinMode.face,
                label: Text('По лицу'),
                icon: Icon(Icons.face_retouching_natural),
              ),
              ButtonSegment(
                value: _CheckinMode.qr,
                label: Text('По QR-коду'),
                icon: Icon(Icons.qr_code_scanner),
              ),
            ],
            selected: {_mode},
            onSelectionChanged: (selection) {
              setState(() {
                _mode = selection.first;
                _errorMessage = null;
                _successMessage = null;
              });
            },
          ),
          const SizedBox(height: AppSpacing.md),
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
                  items: CheckinEventType.values.map((type) {
                    final done = _completedTypes.contains(type);
                    return DropdownMenuItem(
                      value: type,
                      enabled: !done,
                      child: Text(
                        done ? '${type.label} (уже отмечено)' : type.label,
                        style: TextStyle(color: done ? MetrixColors.textMuted : MetrixColors.text),
                      ),
                    );
                  }).toList(),
                  onChanged: (value) {
                    if (value != null) setState(() => _selectedType = value);
                  },
                ),
              ],
            ),
          ),
          if (_mode == _CheckinMode.face) ...[
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
          ],
          if (_mode == _CheckinMode.qr) ...[
            const SizedBox(height: AppSpacing.md),
            AppCard(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  Container(
                    height: 160,
                    width: double.infinity,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: MetrixColors.surfaceMuted,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(Icons.qr_code_scanner, size: 44, color: MetrixColors.textMuted),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  const Text(
                    'Наведите камеру на QR-код на экране точки входа',
                    style: TextStyle(fontSize: 12, color: MetrixColors.textMuted),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  AppButton(
                    label: 'Сканировать QR',
                    icon: Icons.qr_code_scanner,
                    isLoading: _isSubmitting,
                    onPressed: _selectedType == null ? null : _handleScanQr,
                  ),
                ],
              ),
            ),
          ],
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
          if (_mode == _CheckinMode.face)
            AppButton(
              label: 'Отправить отметку',
              isLoading: _isSubmitting,
              onPressed: (_capturedPhoto == null || _selectedType == null) ? null : _handleSubmit,
            ),
        ],
      ),
    );
  }
}