import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'notification_dto.dart';

class NotificationsPage {
  final List<NotificationDto> results;
  final int count;
  final String? next;

  const NotificationsPage({required this.results, required this.count, this.next});
}

class NotificationsRepository {
  final Dio dio;

  NotificationsRepository({required this.dio});

  Future<ApiResult<NotificationsPage>> getNotifications({int page = 1}) async {
    try {
      final response = await dio.get('/api/v1/mobile/notifications/', queryParameters: {
        'page': page,
      });
      final data = response.data as Map<String, dynamic>;
      final results = (data['results'] as List<dynamic>)
          .map((n) => NotificationDto.fromJson(n as Map<String, dynamic>))
          .toList();
      return Success(NotificationsPage(
        results: results,
        count: data['count'] as int,
        next: data['next'] as String?,
      ));
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<ApiResult<void>> markAsRead(int id) async {
    try {
      await dio.post('/api/v1/mobile/notifications/$id/read/');
      return const Success(null);
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось загрузить уведомления';
  }
}