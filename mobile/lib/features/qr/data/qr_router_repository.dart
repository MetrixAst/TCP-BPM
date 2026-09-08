import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'qr_room_repository.dart';
import 'qr_scan_target.dart';

final _uuidPattern = RegExp(
  r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
);

/// Office и round QR кодируют полный веб-URL (страницу подтверждения/скана
/// на сайте) с UUID точки/точки-офиса в хвосте пути — тип отметки зашит не
/// в самом коде, а определяется сервером через rounds/resolve/?qr=<uuid>.
String? _extractAttendanceQrId(String rawValue) {
  final match = _uuidPattern.firstMatch(rawValue);
  return match?.group(0);
}

/// Единая точка входа для QR-сканера: определяет, что за код отсканирован —
/// комната (существующий формат metrix://room/<map_id>, без изменений),
/// офисная точка отметки или точка планового обхода — и возвращает нужный
/// сценарий. Тип отметки (office/round) решает сервер, не клиент.
class QrRouterRepository {
  final Dio dio;

  QrRouterRepository({required this.dio});

  Future<ApiResult<QrScanTarget>> resolve(String rawValue) async {
    final mapId = parseRoomQr(rawValue);
    if (mapId != null) {
      return Success(RoomScanTarget(mapId));
    }

    final qrId = _extractAttendanceQrId(rawValue);
    if (qrId == null) {
      return const Failure('QR-код не распознан');
    }

    try {
      final response = await dio.get(
        '/api/v1/mobile/rounds/resolve/',
        queryParameters: {'qr': qrId},
      );
      final data = response.data as Map<String, dynamic>;

      switch (data['type']) {
        case 'office_checkin':
          return Success(OfficeScanTarget(
            publicId: qrId,
            pointName: data['point_name'] as String? ?? '',
            nextAction: data['next_action'] as String?,
            alreadyDone: data['already_done'] as bool? ?? false,
          ));
        case 'round_point':
          return Success(RoundScanTarget(
            pointUuid: data['point_uuid'] as String? ?? qrId,
            pointName: data['point_name'] as String? ?? '',
            plannedRoundId: data['planned_round_id'] as int?,
          ));
        default:
          return const Failure('QR-код не распознан');
      }
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.response?.statusCode == 404) {
      return 'QR-код не распознан';
    }
    if (e.response?.statusCode == 400) {
      final data = e.response?.data;
      if (data is Map && data['error'] != null) {
        return data['error'].toString();
      }
      return 'QR-код не распознан';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Ошибка сети, попробуйте ещё раз';
  }
}
