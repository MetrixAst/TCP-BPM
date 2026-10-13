import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Адрес BPM-сервера, с которым работает приложение.
///
/// Пользователь не выбирает ТРЦ: при входе Metrix Auth Gateway сам находит его
/// сервер и возвращает адрес, который сохраняется здесь. Без шлюза
/// (AUTH_GATEWAY_URL не задан — разработка) используется BASE_URL из сборки.
class ServerConfig {
  ServerConfig._();

  static const _storageKey = 'server_base_url';
  static const _storage = FlutterSecureStorage();

  static const gatewayUrl = String.fromEnvironment('AUTH_GATEWAY_URL');
  static const buildBaseUrl = String.fromEnvironment(
    'BASE_URL',
    defaultValue: 'https://api.metrix.example.com',
  );

  static String _baseUrl = buildBaseUrl;

  static bool get usesGateway => gatewayUrl.isNotEmpty;

  /// Текущий адрес сервера. Читается перед каждым запросом (см. DioClient).
  static String get baseUrl => _baseUrl;

  /// Восстанавливает сервер последнего входа — вызывается при старте.
  static Future<void> load({FlutterSecureStorage? storage}) async {
    if (!usesGateway) return;
    try {
      final saved = await (storage ?? _storage).read(key: _storageKey);
      if (saved != null && saved.isNotEmpty) _baseUrl = saved;
    } catch (_) {
      // Хранилище недоступно — останемся на адресе из сборки.
    }
  }

  static Future<void> save(String baseUrl, {FlutterSecureStorage? storage}) async {
    _baseUrl = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    await (storage ?? _storage).write(key: _storageKey, value: _baseUrl);
  }
}
