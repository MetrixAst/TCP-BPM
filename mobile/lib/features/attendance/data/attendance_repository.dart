import 'dart:io';

import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'attendance_today_status.dart';

class AttendanceRepository {
  final Dio dio;

  AttendanceRepository({required this.dio});

  Future<ApiResult<void>> checkin({
    required String eventType,
    required File photo,
    double? latitude,
    double? longitude,
    String? idempotencyKey,
  }) async {
    try {
      final formData = FormData.fromMap({
        'event_type': eventType,
        'photo': await MultipartFile.fromFile(photo.path, filename: 'checkin.jpg'),
        if (latitude != null) 'latitude': latitude.toString(),
        if (longitude != null) 'longitude': longitude.toString(),
      });

      await dio.post(
        '/api/v1/mobile/attendance/checkin/',
        data: formData,
        options: idempotencyKey != null
            ? Options(headers: {'Idempotency-Key': idempotencyKey})
            : null,
      );
      return const Success(null);
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<ApiResult<List<AttendanceTodayStatus>>> getToday() async {
      try {
        final response = await dio.get('/api/v1/mobile/attendance/today/');
        final marksJson = response.data['marks'] as List<dynamic>;
        return Success(buildTodayStatus(marksJson));
      } on DioException catch (e) {
        return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
      }
  }

  String _errorMessage(DioException e) {
    if (e.response?.statusCode == 400) {
      final data = e.response?.data;
      if (data is Map && data['error'] != null) {
        return data['error'].toString();
      }
      return 'Отметка уже зафиксирована сегодня';
    }
    if (e.response?.statusCode == 403) {
      return 'Профиль сотрудника не найден';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Ошибка сети, попробуйте ещё раз';
  }
}