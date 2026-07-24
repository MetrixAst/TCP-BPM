import 'package:freezed_annotation/freezed_annotation.dart';

part 'profile_dto.freezed.dart';
part 'profile_dto.g.dart';

@freezed
class EmployeeInfoDto with _$EmployeeInfoDto {
  const factory EmployeeInfoDto({
    String? department,
    String? position,
    required String status,
    required String phone,
    @JsonKey(name: 'hire_date') String? hireDate,
    required bool head,
  }) = _EmployeeInfoDto;

  factory EmployeeInfoDto.fromJson(Map<String, dynamic> json) =>
      _$EmployeeInfoDtoFromJson(json);
}

@freezed
class ProfileDto with _$ProfileDto {
  const factory ProfileDto({
    required int id,
    required String username,
    @JsonKey(name: 'full_name') required String fullName,
    required String role,
    required String email,
    String? avatar,
    EmployeeInfoDto? employee,
  }) = _ProfileDto;

  factory ProfileDto.fromJson(Map<String, dynamic> json) =>
      _$ProfileDtoFromJson(json);
}