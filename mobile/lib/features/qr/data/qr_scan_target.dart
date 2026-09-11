/// Куда ведёт отсканированный QR — определяется сервером (rounds/resolve/),
/// кроме комнатного QR, который парсится на клиенте по формату
/// metrix://room/<map_id> (как и раньше, без изменений).
sealed class QrScanTarget {
  const QrScanTarget();
}

class RoomScanTarget extends QrScanTarget {
  final String mapId;
  const RoomScanTarget(this.mapId);
}

class OfficeScanTarget extends QrScanTarget {
  final String publicId;
  final String pointName;
  final String? nextAction; // 'day_start' | 'day_end' | null (уже всё отмечено)
  final bool alreadyDone;

  const OfficeScanTarget({
    required this.publicId,
    required this.pointName,
    required this.nextAction,
    required this.alreadyDone,
  });
}

class RoundScanTarget extends QrScanTarget {
  final String pointUuid;
  final String pointName;
  final int? plannedRoundId; // null — на сегодня обход по этой точке не назначен

  const RoundScanTarget({
    required this.pointUuid,
    required this.pointName,
    required this.plannedRoundId,
  });
}
