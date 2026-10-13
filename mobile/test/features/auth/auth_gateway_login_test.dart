// Запуск: flutter test --dart-define=AUTH_GATEWAY_URL=https://gw.test test/features/auth/auth_gateway_login_test.dart
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:metrix_app/core/database/local_data_cleaner.dart';
import 'package:metrix_app/core/network/api_result.dart';
import 'package:metrix_app/core/network/server_config.dart';
import 'package:metrix_app/features/auth/data/auth_repository.dart';
import 'package:metrix_app/features/auth/data/auth_tokens.dart';

class MockDio extends Mock implements Dio {}
class MockSecureStorage extends Mock implements FlutterSecureStorage {}
class MockLocalDataCleaner extends Mock implements LocalDataCleaner {}

void main() {
  late MockDio dio;
  late MockDio gateway;
  late MockSecureStorage storage;
  late AuthRepository repository;

  setUp(() {
    dio = MockDio();
    gateway = MockDio();
    storage = MockSecureStorage();
    final cleaner = MockLocalDataCleaner();
    repository = AuthRepository(dio: dio, storage: storage, localDataCleaner: cleaner, gatewayDio: gateway);

    when(() => dio.options).thenReturn(BaseOptions(baseUrl: 'https://old.example.com'));
    when(() => storage.read(key: any(named: 'key'))).thenAnswer((_) async => null);
    when(() => storage.write(key: any(named: 'key'), value: any(named: 'value'))).thenAnswer((_) async {});
    when(() => cleaner.clear()).thenAnswer((_) async {});
  });

  test('вход через шлюз запоминает сервер ТРЦ', () async {
    when(() => gateway.post('/api/login', data: any(named: 'data'))).thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/login'),
        statusCode: 200,
        data: {'access': 'a1', 'refresh': 'r1', 'base_url': 'https://bpm.mega.kz/'},
      ),
    );

    final result = await repository.login(username: 'ivanov', password: 'p');

    expect(result, isA<Success<AuthTokens>>());
    expect(ServerConfig.baseUrl, 'https://bpm.mega.kz');
    verify(() => storage.write(key: 'server_base_url', value: 'https://bpm.mega.kz')).called(1);
    verify(() => storage.write(key: 'auth_access_token', value: 'a1')).called(1);
    verifyNever(() => dio.post('/api/token/', data: any(named: 'data')));
  }, skip: ServerConfig.usesGateway ? false : 'нужен --dart-define=AUTH_GATEWAY_URL');

  test('неверный логин — общее сообщение', () async {
    when(() => gateway.post('/api/login', data: any(named: 'data'))).thenThrow(DioException(
      requestOptions: RequestOptions(path: '/api/login'),
      response: Response(requestOptions: RequestOptions(path: '/api/login'), statusCode: 401),
      type: DioExceptionType.badResponse,
    ));

    final result = await repository.login(username: 'nobody', password: 'p');

    expect((result as Failure).message, 'Неверный логин или пароль');
  }, skip: ServerConfig.usesGateway ? false : 'нужен --dart-define=AUTH_GATEWAY_URL');
}
