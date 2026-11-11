import 'package:flutter_test/flutter_test.dart';
import 'package:metrix_app/features/profile/presentation/profile_screen.dart';

void main() {
  test('статус сотрудника показывается по-русски', () {
    expect(employeeStatusLabel('active'), 'Активен');
    expect(employeeStatusLabel('dismissed'), 'Уволен');
    expect(employeeStatusLabel('vacation'), 'В отпуске');
    expect(employeeStatusLabel('sick_leave'), 'На больничном');
    expect(employeeStatusLabel('unknown'), 'unknown');
  });
}
