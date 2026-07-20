class TenantPaymentDto {
  final int id;
  final String tenantName;
  final String contractNumber;
  final String period;
  final String charged;
  final String paid;
  final String balance;
  final String? plannedDate;
  final String? actualDate;
  final int overdueDays;
  final String status;
  final String statusDisplay;

  const TenantPaymentDto({
    required this.id,
    required this.tenantName,
    required this.contractNumber,
    required this.period,
    required this.charged,
    required this.paid,
    required this.balance,
    this.plannedDate,
    this.actualDate,
    required this.overdueDays,
    required this.status,
    required this.statusDisplay,
  });

  factory TenantPaymentDto.fromJson(Map<String, dynamic> json) {
    return TenantPaymentDto(
      id: json['id'] as int,
      tenantName: json['tenant_name'] as String? ?? '—',
      contractNumber: json['contract_number'] as String? ?? '',
      period: json['period'] as String,
      charged: json['charged'].toString(),
      paid: json['paid'].toString(),
      balance: json['balance'].toString(),
      plannedDate: json['planned_date'] as String?,
      actualDate: json['actual_date'] as String?,
      overdueDays: json['overdue_days'] as int? ?? 0,
      status: json['status'] as String,
      statusDisplay: json['status_display'] as String,
    );
  }
}

class PaymentCalendarEntryDto {
  final int id;
  final String tenantName;
  final String contractNumber;
  final String expectedDate;
  final String expectedAmount;
  final String? actualAmount;
  final String? actualDate;
  final String status;
  final String statusDisplay;

  const PaymentCalendarEntryDto({
    required this.id,
    required this.tenantName,
    required this.contractNumber,
    required this.expectedDate,
    required this.expectedAmount,
    this.actualAmount,
    this.actualDate,
    required this.status,
    required this.statusDisplay,
  });

  factory PaymentCalendarEntryDto.fromJson(Map<String, dynamic> json) {
    return PaymentCalendarEntryDto(
      id: json['id'] as int,
      tenantName: json['tenant_name'] as String? ?? '—',
      contractNumber: json['contract_number'] as String? ?? '',
      expectedDate: json['expected_date'] as String,
      expectedAmount: json['expected_amount'].toString(),
      actualAmount: json['actual_amount']?.toString(),
      actualDate: json['actual_date'] as String?,
      status: json['status'] as String,
      statusDisplay: json['status_display'] as String,
    );
  }
}