import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'ticket_detail_dto.dart';
import 'ticket_message_dto.dart';

class TicketDetailRepository {
  final Dio dio;

  TicketDetailRepository({required this.dio});

  Future<ApiResult<TicketDetailDto>> getTicket(int id) async {
    try {
      final response = await dio.get('/api/v1/mobile/tickets/$id/');
      return Success(TicketDetailDto.fromJson(response.data as Map<String, dynamic>));
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<ApiResult<List<TicketMessageDto>>> getMessages(int ticketId) async {
    try {
      final response = await dio.get('/api/v1/mobile/tickets/$ticketId/messages/');
      final data = response.data as Map<String, dynamic>;
      final results = (data['results'] as List<dynamic>)
          .map((m) => TicketMessageDto.fromJson(m as Map<String, dynamic>))
          .toList();
      return Success(results);
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<ApiResult<TicketMessageDto>> sendMessage(int ticketId, String text) async {
    try {
      final response = await dio.post(
        '/api/v1/mobile/tickets/$ticketId/messages/',
        data: {'text': text},
      );
      return Success(TicketMessageDto.fromJson(response.data as Map<String, dynamic>));
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.response?.statusCode == 404) {
      return 'Заявка не найдена';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Ошибка сети, попробуйте ещё раз';
  }
}