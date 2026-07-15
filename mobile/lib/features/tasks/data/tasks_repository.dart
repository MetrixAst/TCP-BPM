import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'task_dto.dart';

class TasksPage {
  final List<TaskDto> results;
  final int count;
  final String? next;

  const TasksPage({required this.results, required this.count, this.next});
}

class TasksRepository {
  final Dio dio;

  TasksRepository({required this.dio});

  Future<ApiResult<TasksPage>> getTasks({
    int? executorId,
    String? status,
    String? priority,
    int page = 1,
  }) async {
    try {
      final response = await dio.get('/api/v1/tasks/', queryParameters: {
        if (executorId != null) 'executor': executorId,
        if (status != null) 'status': status,
        if (priority != null) 'priority': priority,
        'page': page,
      });

      final data = response.data as Map<String, dynamic>;
      final results = (data['results'] as List<dynamic>)
          .map((t) => TaskDto.fromJson(t as Map<String, dynamic>))
          .toList();

      return Success(TasksPage(
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
    return 'Не удалось загрузить задачи';
  }
}