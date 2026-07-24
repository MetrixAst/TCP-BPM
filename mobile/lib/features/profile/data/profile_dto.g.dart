// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'profile_dto.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$EmployeeInfoDtoImpl _$$EmployeeInfoDtoImplFromJson(
  Map<String, dynamic> json,
) => _$EmployeeInfoDtoImpl(
  department: json['department'] as String?,
  position: json['position'] as String?,
  status: json['status'] as String,
  phone: json['phone'] as String,
  hireDate: json['hire_date'] as String?,
  head: json['head'] as bool,
);

Map<String, dynamic> _$$EmployeeInfoDtoImplToJson(
  _$EmployeeInfoDtoImpl instance,
) => <String, dynamic>{
  'department': instance.department,
  'position': instance.position,
  'status': instance.status,
  'phone': instance.phone,
  'hire_date': instance.hireDate,
  'head': instance.head,
};

_$ProfileDtoImpl _$$ProfileDtoImplFromJson(Map<String, dynamic> json) =>
    _$ProfileDtoImpl(
      id: (json['id'] as num).toInt(),
      username: json['username'] as String,
      fullName: json['full_name'] as String,
      role: json['role'] as String,
      email: json['email'] as String,
      avatar: json['avatar'] as String?,
      employee: json['employee'] == null
          ? null
          : EmployeeInfoDto.fromJson(json['employee'] as Map<String, dynamic>),
    );

Map<String, dynamic> _$$ProfileDtoImplToJson(_$ProfileDtoImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'username': instance.username,
      'full_name': instance.fullName,
      'role': instance.role,
      'email': instance.email,
      'avatar': instance.avatar,
      'employee': instance.employee,
    };
