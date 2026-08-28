import 'package:dio/dio.dart';

import '../../../core/network/api_result.dart';

class RoomDto {
  final int id;
  final String number;
  final String mapId;
  final int floor;

  const RoomDto({
    required this.id,
    required this.number,
    required this.mapId,
    required this.floor,
  });

  factory RoomDto.fromJson(Map<String, dynamic> json) {
    return RoomDto(
      id: json['id'] as int,
      number: json['number'] as String,
      mapId: json['map_id'] as String,
      floor: json['floor'] as int,
    );
  }
}

/// Парсит QR-текст формата metrix://room/<map_id>, возвращает map_id или null.
String? parseRoomQr(String rawValue) {
  final uri = Uri.tryParse(rawValue);
  if (uri == null || uri.scheme != 'metrix' || uri.host != 'room') {
    return null;
  }
  final mapId = uri.path.replaceFirst('/', '');
  return mapId.isNotEmpty ? mapId : null;
}

class QrRoomRepository {
  final Dio dio;

  QrRoomRepository({required this.dio});

  Future<ApiResult<RoomDto>> resolveRoom(String mapId) async {
    try {
      final response = await dio.get(
        '/api/v1/mobile/rooms/resolve/',
        queryParameters: {'map_id': mapId},
      );
      return Success(RoomDto.fromJson(response.data as Map<String, dynamic>));
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        return const Failure('Помещение не найдено', statusCode: 404);
      }
      return Failure(_errorMessage(e), statusCode: e.response?.statusCode);
    }
  }

  String _errorMessage(DioException e) {
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return 'Сервер не отвечает, проверьте соединение';
    }
    return 'Не удалось распознать QR-код';
  }
}