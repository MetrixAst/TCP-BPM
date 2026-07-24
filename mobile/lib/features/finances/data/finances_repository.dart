import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'finance_dto.dart';

class FinancesRepository {
  final Dio dio;

  FinancesRepository({required this.dio});

  Future<ApiResult<List<TenantPaymentDto>>> getPayments({int page = 1}) async {
    try {
      final response = await dio.get('/api/v1/finances/payments/', queryParameters: {'page': page});
      final data = response.data as Map<String, dynamic>;
      final results = (data['results'] as List<dynamic>)
          .map((p) => TenantPaymentDto.fromJson(p as Map<String, dynamic>))
          .toList();
      return Success(results);
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<ApiResult<List<PaymentCalendarEntryDto>>> getCalendar({int page = 1}) async {
    try {
      final response = await dio.get('/api/v1/finances/calendar/', queryParameters: {'page': page});
      final data = response.data as Map<String, dynamic>;
      final results = (data['results'] as List<dynamic>)
          .map((c) => PaymentCalendarEntryDto.fromJson(c as Map<String, dynamic>))
          .toList();
      return Success(results);
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.response?.statusCode == 403) {
      return 'Нет доступа к финансовым данным';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось загрузить данные';
  }
}