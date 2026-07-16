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

  Future<ApiResult<TaskDto>> getTask(int id) async {
    try {
      final response = await dio.get('/api/v1/tasks/$id/');
      return Success(TaskDto.fromJson(response.data as Map<String, dynamic>));
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<ApiResult<TaskDto>> transition(int id, String action) async {
    try {
      final response = await dio.post(
        '/api/v1/tasks/$id/transition/',
        data: {'action': action},
      );
      return Success(TaskDto.fromJson(response.data as Map<String, dynamic>));
    } on DioException catch (e) {
      return Failure(_transitionErrorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось загрузить задачи';
  }

  String _transitionErrorMessage(DioException e) {
    if (e.response?.statusCode == 403) {
      return 'Недостаточно прав для этого действия';
    }
    if (e.response?.statusCode == 400) {
      final data = e.response?.data;
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
      return 'Не удалось выполнить действие';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Ошибка сети, попробуйте ещё раз';
  }
}