import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../../core/network/api_result.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../attendance/data/attendance_repository.dart';
import '../data/qr_scan_target.dart';

/// Preview + подтверждение отметки по офисному QR (BE-FT-01). Тип отметки
/// (приход/уход) уже пришёл в [target.nextAction] из rounds/resolve/ —
/// сервер тот же самый решает, что писать, и в момент самого POST (на
/// случай если между preview и подтверждением сотрудник уже отметился
/// откуда-то ещё — тогда просто вернётся already_done).
class OfficeQrConfirmScreen extends StatefulWidget {
  final OfficeScanTarget target;

  const OfficeQrConfirmScreen({super.key, required this.target});

  @override
  State<OfficeQrConfirmScreen> createState() => _OfficeQrConfirmScreenState();
}

class _OfficeQrConfirmScreenState extends State<OfficeQrConfirmScreen> {
  late final AttendanceRepository _repository;
  bool _isSubmitting = false;
  bool _done = false;
  String? _resultMessage;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _repository = AttendanceRepository(dio: DioClient().dio);
  }

  String _actionLabel(String? action) {
    switch (action) {
      case 'day_start':
        return 'Подтвердите приход';
      case 'day_end':
        return 'Подтвердите уход';
      default:
        return 'Подтвердите отметку';
    }
  }

  Future<void> _confirm() async {
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final result = await _repository.checkinOfficeQr(
      publicId: widget.target.publicId,
      idempotencyKey: const Uuid().v4(),
    );

    if (!mounted) return;

    setState(() {
      _isSubmitting = false;
      switch (result) {
        case Success(:final data):
          _done = true;
          _resultMessage = data['message'] as String? ?? 'Отметка сохранена';
        case Failure(:final message):
          _errorMessage = message;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final target = widget.target;
    final alreadyDone = target.alreadyDone || _done;

    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Отметка посещаемости'),
      body: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: AppCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const Icon(Icons.location_city, size: 40, color: MetrixColors.primary),
              const SizedBox(height: AppSpacing.sm),
              Text(
                target.pointName,
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: MetrixColors.text),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.lg),
              if (alreadyDone) ...[
                const Icon(Icons.check_circle_rounded, size: 40, color: MetrixColors.accent),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  _resultMessage ?? 'Отметки на сегодня уже сделаны',
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: MetrixColors.accent),
                  textAlign: TextAlign.center,
                ),
              ] else ...[
                Text(
                  _actionLabel(target.nextAction),
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: MetrixColors.text),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.md),
                if (_errorMessage != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Text(_errorMessage!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
                  ),
                SizedBox(
                  width: double.infinity,
                  child: AppButton(
                    label: 'Подтвердить',
                    isLoading: _isSubmitting,
                    onPressed: _confirm,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
