import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';
import 'profile_dto.dart';

class ProfileRepository {
  final Dio dio;

  ProfileRepository({required this.dio});

  Future<ApiResult<ProfileDto>> getProfile() async {
    try {
      final response = await dio.get('/api/v1/mobile/me/');
      final profileJson = response.data['profile'] as Map<String, dynamic>;
      final profile = ProfileDto.fromJson(profileJson);
      return Success(profile);
    } on DioException catch (e) {
      return Failure(
        _errorMessage(e),
        statusCode: e.response?.statusCode,
      );
    }
  }

  String _errorMessage(DioException e) {
    if (e.response?.statusCode == 401) {
      return 'Сессия истекла, войдите заново';
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось загрузить профиль';
  }
}