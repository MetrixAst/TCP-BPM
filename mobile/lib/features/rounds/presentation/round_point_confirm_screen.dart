import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';

import '../../../core/network/api_result.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../qr/data/qr_scan_target.dart';
import '../data/round_item_answer.dart';
import '../data/round_point_detail.dart';
import '../data/rounds_repository.dart';

class RoundPointConfirmScreen extends StatefulWidget {
  final RoundScanTarget target;

  const RoundPointConfirmScreen({super.key, required this.target});

  @override
  State<RoundPointConfirmScreen> createState() => _RoundPointConfirmScreenState();
}

class _RoundPointConfirmScreenState extends State<RoundPointConfirmScreen> {
  late final RoundsRepository _repository;

  bool _isLoading = true;
  bool _isSubmitting = false;
  bool _done = false;
  String? _loadError;
  String? _submitError;
  RoundPointDetail? _detail;

  final Map<int, bool> _passed = {};
  final Map<int, TextEditingController> _comments = {};
  final Map<int, String> _photoPaths = {};
  final _overallCommentController = TextEditingController();
  double? _latitude;
  double? _longitude;

  @override
  void initState() {
    super.initState();
    _repository = RoundsRepository(dio: DioClient().dio);
    _load();
    _resolveLocation();
  }

  @override
  void dispose() {
    _overallCommentController.dispose();
    for (final c in _comments.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _resolveLocation() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return;
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        return;
      }
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 8)),
      );
      if (!mounted) return;
      setState(() {
        _latitude = position.latitude;
        _longitude = position.longitude;
      });
    } catch (_) {
      // best-effort — как и на вебе, отсутствие геолокации не блокирует обход
    }
  }

  Future<void> _load() async {
    final result = await _repository.getPointDetail(widget.target.pointUuid);
    if (!mounted) return;
    setState(() {
      _isLoading = false;
      switch (result) {
        case Success(:final data):
          _detail = data;
          for (final item in data.items) {
            _comments[item.id] = TextEditingController();
          }
        case Failure(:final message):
          _loadError = message;
      }
    });
  }

  Future<void> _pickPhoto(int itemId) async {
    try {
      final xFile = await ImagePicker().pickImage(source: ImageSource.camera, imageQuality: 80);
      if (xFile == null || !mounted) return;
      setState(() => _photoPaths[itemId] = xFile.path);
    } catch (_) {
      // отмена съёмки — просто не сохраняем фото
    }
  }

  bool get _allAnswered {
    final detail = _detail;
    if (detail == null) return false;
    if (detail.items.isEmpty) return true;
    return detail.items.every((item) => _passed.containsKey(item.id));
  }

  bool get _missingRequiredPhoto {
    final detail = _detail;
    if (detail == null) return false;
    for (final item in detail.items) {
      final passed = _passed[item.id];
      if (passed == false && item.requiresPhotoOnFail && _photoPaths[item.id] == null) {
        return true;
      }
    }
    return false;
  }

  Future<void> _submit() async {
    final plannedRoundId = widget.target.plannedRoundId;
    if (plannedRoundId == null) return;

    setState(() {
      _isSubmitting = true;
      _submitError = null;
    });

    final answers = (_detail?.items ?? const <RoundChecklistItem>[]).map((item) {
      return RoundItemAnswer(
        itemId: item.id,
        passed: _passed[item.id] ?? true,
        comment: _comments[item.id]?.text ?? '',
        photoPath: _photoPaths[item.id],
      );
    }).toList();

    final result = await _repository.submitPointAnswer(
      plannedRoundId: plannedRoundId,
      pointUuid: widget.target.pointUuid,
      answers: answers,
      comment: _overallCommentController.text,
      latitude: _latitude,
      longitude: _longitude,
      idempotencyKey: const Uuid().v4(),
    );

    if (!mounted) return;

    setState(() {
      _isSubmitting = false;
      switch (result) {
        case Success():
          _done = true;
        case Failure(:final message):
          _submitError = message;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: AppTopBar(title: widget.target.pointName),
      body: _isLoading ? const Center(child: CircularProgressIndicator()) : _buildBody(),
    );
  }

  Widget _buildBody() {
    if (widget.target.plannedRoundId == null) {
      return _buildInfoState(
        icon: Icons.event_busy_rounded,
        color: MetrixColors.warning,
        text: 'На сегодня у вас нет назначенного обхода по этой точке',
      );
    }

    if (_loadError != null) {
      return _buildInfoState(icon: Icons.error_outline_rounded, color: MetrixColors.danger, text: _loadError!);
    }

    if (_done) {
      return _buildInfoState(icon: Icons.check_circle_rounded, color: MetrixColors.accent, text: 'Точка отмечена');
    }

    final detail = _detail;
    if (detail == null) {
      return _buildInfoState(icon: Icons.error_outline_rounded, color: MetrixColors.danger, text: 'Не удалось загрузить точку');
    }

    if (detail.alreadyVisited) {
      return _buildInfoState(icon: Icons.check_circle_rounded, color: MetrixColors.accent, text: 'Точка уже отмечена сегодня');
    }

    if (detail.items.isEmpty) {
      return _buildInfoState(
        icon: Icons.info_outline_rounded,
        color: MetrixColors.textMuted,
        text: 'Этой точке ещё не назначен чек-лист. Обратитесь к администратору.',
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (detail.location.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: Text(detail.location, style: const TextStyle(color: MetrixColors.textMuted, fontSize: 13)),
            ),
          for (final item in detail.items) ...[
            _buildItemCard(item),
            const SizedBox(height: AppSpacing.sm),
          ],
          AppCard(
            child: TextField(
              controller: _overallCommentController,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                border: InputBorder.none,
                hintText: 'Комментарий по обходу (необязательно)',
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          if (_submitError != null)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Text(_submitError!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
            ),
          AppButton(
            label: 'Завершить обход',
            isLoading: _isSubmitting,
            onPressed: (_allAnswered && !_missingRequiredPhoto) ? _submit : null,
          ),
          if (_allAnswered && _missingRequiredPhoto)
            const Padding(
              padding: EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                'Для пунктов с несоответствием, где требуется фото — приложите снимок',
                style: TextStyle(color: MetrixColors.warning, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildItemCard(RoundChecklistItem item) {
    final passed = _passed[item.id];
    final showExtra = passed == false;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(item.text, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5, color: MetrixColors.text)),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Expanded(
                child: _ToggleChip(
                  label: '✓ Соответствует',
                  isActive: passed == true,
                  activeColor: MetrixColors.accent,
                  onTap: () => setState(() => _passed[item.id] = true),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _ToggleChip(
                  label: '✕ Не соответствует',
                  isActive: passed == false,
                  activeColor: MetrixColors.danger,
                  onTap: () => setState(() => _passed[item.id] = false),
                ),
              ),
            ],
          ),
          if (showExtra) ...[
            const SizedBox(height: AppSpacing.sm),
            TextField(
              controller: _comments[item.id],
              minLines: 1,
              maxLines: 3,
              decoration: const InputDecoration(
                isDense: true,
                border: OutlineInputBorder(),
                hintText: 'Что не так?',
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            OutlinedButton.icon(
              onPressed: () => _pickPhoto(item.id),
              icon: const Icon(Icons.camera_alt_outlined, size: 18),
              label: Text(_photoPaths[item.id] == null ? 'Добавить фото' : 'Фото приложено'),
            ),
            if (item.requiresPhotoOnFail)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text('Фото обязательно при несоответствии', style: TextStyle(fontSize: 11, color: MetrixColors.textMuted)),
              ),
          ],
        ],
      ),
    );
  }

  Widget _buildInfoState({required IconData icon, required Color color, required String text}) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 44, color: color),
            const SizedBox(height: AppSpacing.sm),
            Text(text, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: color), textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _ToggleChip extends StatelessWidget {
  final String label;
  final bool isActive;
  final Color activeColor;
  final VoidCallback onTap;

  const _ToggleChip({
    required this.label,
    required this.isActive,
    required this.activeColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: isActive ? activeColor.withValues(alpha: 0.12) : Colors.white,
          border: Border.all(color: isActive ? activeColor : MetrixColors.border),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          label,
          style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: isActive ? activeColor : MetrixColors.textMuted),
        ),
      ),
    );
  }
}
