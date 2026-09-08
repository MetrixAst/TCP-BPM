import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'round_item_answer.dart';
import 'round_point_detail.dart';

class RoundsRepository {
  final Dio dio;

  RoundsRepository({required this.dio});

  Future<ApiResult<RoundPointDetail>> getPointDetail(String pointUuid) async {
    try {
      final response = await dio.get('/api/v1/mobile/rounds/points/$pointUuid/');
      return Success(RoundPointDetail.fromJson(response.data as Map<String, dynamic>));
    } on DioException catch (e) {
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  Future<ApiResult<Map<String, dynamic>>> submitPointAnswer({
    required int plannedRoundId,
    required String pointUuid,
    required List<RoundItemAnswer> answers,
    String comment = '',
    double? latitude,
    double? longitude,
    String? idempotencyKey,
  }) async {
    try {
      final map = <String, dynamic>{
        'comment': comment,
        if (latitude != null) 'latitude': latitude.toString(),
        if (longitude != null) 'longitude': longitude.toString(),
      };
      for (final answer in answers) {
        map['item_${answer.itemId}_status'] = answer.passed ? 'ok' : 'fail';
        map['item_${answer.itemId}_comment'] = answer.comment;
        if (answer.photoPath != null) {
          map['item_${answer.itemId}_photo'] = await MultipartFile.fromFile(
            answer.photoPath!,
            filename: 'defect_${answer.itemId}.jpg',
          );
        }
      }

      final response = await dio.post(
        '/api/v1/mobile/rounds/$plannedRoundId/points/$pointUuid/answer/',
        data: FormData.fromMap(map),
        options: idempotencyKey != null
            ? Options(headers: {'Idempotency-Key': idempotencyKey})
            : null,
      );
      return Success(response.data as Map<String, dynamic>);
    } on DioException catch (e) {
      return Failure(_answerErrorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.response?.statusCode == 404) {
      return 'Точка не найдена';
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

  String _answerErrorMessage(DioException e) {
    final status = e.response?.statusCode;
    if (status == 403) {
      final data = e.response?.data;
      if (data is Map && data['error'] != null) {
        return data['error'].toString();
      }
      return 'На сегодня у вас нет назначенного обхода по этой точке';
    }
    if (status == 404) {
      return 'Точка не найдена';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Ошибка сети, попробуйте ещё раз';
  }
}
