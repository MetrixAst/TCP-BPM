import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'ticket_dto.dart';
import 'dart:io';

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

  Future<ApiResult<TicketDto>> createTicket({
    required String title,
    required String description,
    required String category,
    String? priority,
    String? room,
    File? photo,
  }) async {
    try {
      final formData = FormData.fromMap({
        'title': title,
        'description': description,
        'category': category,
        if (priority != null) 'priority': priority,
        if (room != null && room.isNotEmpty) 'room': room,
        if (photo != null)
          'photo': await MultipartFile.fromFile(photo.path, filename: 'ticket.jpg'),
      });

      final response = await dio.post('/api/v1/mobile/tickets/', data: formData);
      return Success(TicketDto.fromJson(response.data as Map<String, dynamic>));
    } on DioException catch (e) {
      return Failure(_createErrorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _createErrorMessage(DioException e) {
    if (e.response?.statusCode == 400) {
      final data = e.response?.data;
      if (data is Map && data.isNotEmpty) {
        final firstError = data.values.first;
        if (firstError is List && firstError.isNotEmpty) {
          return firstError.first.toString();
        }
        return firstError.toString();
      }
      return 'Проверьте правильность заполнения формы';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось создать заявку';
  }
  
  String _errorMessage(DioException e) {
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось загрузить заявки';
  }
}