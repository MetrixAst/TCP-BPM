import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'ticket_dto.dart';

class TicketsPage {
  final List<TicketDto> results;
  final int count;
  final String? next;

  const TicketsPage({required this.results, required this.count, this.next});
}

class TicketsRepository {
  final Dio dio;

  TicketsRepository({required this.dio});

  Future<ApiResult<TicketsPage>> getTickets({
    String? status,
    String? category,
    int page = 1,
  }) async {
    try {
      final response = await dio.get('/api/v1/mobile/tickets/', queryParameters: {
        if (status != null) 'status': status,
        if (category != null) 'category': category,
        'page': page,
      });

      final data = response.data as Map<String, dynamic>;
      final results = (data['results'] as List<dynamic>)
          .map((t) => TicketDto.fromJson(t as Map<String, dynamic>))
          .toList();

      return Success(TicketsPage(
        results: results,
        count: data['count'] as int,
        next: data['next'] as String?,
      ));
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось загрузить заявки';
  }
}