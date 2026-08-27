import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'ticket_dto.dart';
import 'dart:io';
import 'dart:convert';
import '../../../core/database/app_database.dart';
import 'package:drift/drift.dart';

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

      // Кэшируем первую страницу без фильтров — именно её показываем офлайн
      if (page == 1 && status == null && category == null) {
        await _cacheTickets(results);
      }

      return Success(TicketsPage(
        results: results,
        count: data['count'] as int,
        next: data['next'] as String?,
      ));
    } on DioException catch (e) {
      // Если сети нет и это первая страница без фильтров — отдаём кэш
      if (page == 1 && status == null && category == null) {
        final cached = await _readCachedTickets();
        if (cached.isNotEmpty) {
          return Success(TicketsPage(results: cached, count: cached.length, next: null));
        }
      }
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<void> _cacheTickets(List<TicketDto> tickets) async {
    final db = AppDatabase.instance;
    await db.batch((batch) {
      batch.deleteAll(db.cachedTickets);
      batch.insertAll(
        db.cachedTickets,
        tickets.map((t) => CachedTicketsCompanion.insert(
              id: Value(t.id),
              dataJson: jsonEncode({
                'id': t.id,
                'number': t.number,
                'title': t.title,
                'category': t.category,
                'priority': t.priority,
                'status': t.status,
                'room': t.room,
                'created_at': t.createdAt,
                'photo': t.photo,
              }),
            )),
      );
    });
  }

  Future<List<TicketDto>> _readCachedTickets() async {
    final db = AppDatabase.instance;
    final rows = await db.select(db.cachedTickets).get();
    return rows
        .map((r) => TicketDto.fromJson(jsonDecode(r.dataJson) as Map<String, dynamic>))
        .toList();
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
    if (e.response?.statusCode == 403) {
      return 'У вас нет доступа к этому разделу';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось загрузить заявки';
  }
}