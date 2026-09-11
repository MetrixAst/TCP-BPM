import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_result.dart';
import '../../../core/network/dio_client.dart';
import '../data/qr_room_repository.dart';
import '../data/qr_router_repository.dart';
import '../data/qr_scan_target.dart';

/// Единая точка входа для кнопки "Скан QR" где бы она ни была — открывает
/// сканер, определяет сценарий (комната / офисная точка / точка обхода) и
/// ведёт в нужный экран. Комнатный сценарий — тот же самый вызов
/// resolveRoom + переход на создание заявки, что был и раньше, один в один,
/// чтобы не сломать регрессией существующий флоу.
Future<void> handleQrScan(BuildContext context) async {
  final rawValue = await context.push<String>('/qr-scanner');
  if (rawValue == null || !context.mounted) return;

  final router = QrRouterRepository(dio: DioClient().dio);
  final result = await router.resolve(rawValue);

  if (!context.mounted) return;

  switch (result) {
    case Success(:final data):
      switch (data) {
        case RoomScanTarget(:final mapId):
          await _handleRoom(context, mapId);
        case OfficeScanTarget():
          await context.push('/attendance/office-confirm', extra: data);
        case RoundScanTarget():
          await context.push('/rounds/point-confirm', extra: data);
      }
    case Failure(:final message):
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }
}

Future<void> _handleRoom(BuildContext context, String mapId) async {
  final repository = QrRoomRepository(dio: DioClient().dio);
  final roomResult = await repository.resolveRoom(mapId);

  if (!context.mounted) return;

  switch (roomResult) {
    case Success(:final data):
      context.push('/tickets/create?room=${Uri.encodeComponent(data.number)}');
    case Failure(:final message):
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }
}
