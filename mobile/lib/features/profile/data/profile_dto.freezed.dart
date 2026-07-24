// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'profile_dto.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
  'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models',
);

EmployeeInfoDto _$EmployeeInfoDtoFromJson(Map<String, dynamic> json) {
  return _EmployeeInfoDto.fromJson(json);
}

/// @nodoc
mixin _$EmployeeInfoDto {
  String? get department => throw _privateConstructorUsedError;
  String? get position => throw _privateConstructorUsedError;
  String get status => throw _privateConstructorUsedError;
  String get phone => throw _privateConstructorUsedError;
  @JsonKey(name: 'hire_date')
  String? get hireDate => throw _privateConstructorUsedError;
  bool get head => throw _privateConstructorUsedError;

  /// Serializes this EmployeeInfoDto to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of EmployeeInfoDto
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $EmployeeInfoDtoCopyWith<EmployeeInfoDto> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $EmployeeInfoDtoCopyWith<$Res> {
  factory $EmployeeInfoDtoCopyWith(
    EmployeeInfoDto value,
    $Res Function(EmployeeInfoDto) then,
  ) = _$EmployeeInfoDtoCopyWithImpl<$Res, EmployeeInfoDto>;
  @useResult
  $Res call({
    String? department,
    String? position,
    String status,
    String phone,
    @JsonKey(name: 'hire_date') String? hireDate,
    bool head,
  });
}

/// @nodoc
class _$EmployeeInfoDtoCopyWithImpl<$Res, $Val extends EmployeeInfoDto>
    implements $EmployeeInfoDtoCopyWith<$Res> {
  _$EmployeeInfoDtoCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of EmployeeInfoDto
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? department = freezed,
    Object? position = freezed,
    Object? status = null,
    Object? phone = null,
    Object? hireDate = freezed,
    Object? head = null,
  }) {
    return _then(
      _value.copyWith(
            department: freezed == department
                ? _value.department
                : department // ignore: cast_nullable_to_non_nullable
                      as String?,
            position: freezed == position
                ? _value.position
                : position // ignore: cast_nullable_to_non_nullable
                      as String?,
            status: null == status
                ? _value.status
                : status // ignore: cast_nullable_to_non_nullable
                      as String,
            phone: null == phone
                ? _value.phone
                : phone // ignore: cast_nullable_to_non_nullable
                      as String,
            hireDate: freezed == hireDate
                ? _value.hireDate
                : hireDate // ignore: cast_nullable_to_non_nullable
                      as String?,
            head: null == head
                ? _value.head
                : head // ignore: cast_nullable_to_non_nullable
                      as bool,
          )
          as $Val,
    );
  }
}

/// @nodoc
abstract class _$$EmployeeInfoDtoImplCopyWith<$Res>
    implements $EmployeeInfoDtoCopyWith<$Res> {
  factory _$$EmployeeInfoDtoImplCopyWith(
    _$EmployeeInfoDtoImpl value,
    $Res Function(_$EmployeeInfoDtoImpl) then,
  ) = __$$EmployeeInfoDtoImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({
    String? department,
    String? position,
    String status,
    String phone,
    @JsonKey(name: 'hire_date') String? hireDate,
    bool head,
  });
}

/// @nodoc
class __$$EmployeeInfoDtoImplCopyWithImpl<$Res>
    extends _$EmployeeInfoDtoCopyWithImpl<$Res, _$EmployeeInfoDtoImpl>
    implements _$$EmployeeInfoDtoImplCopyWith<$Res> {
  __$$EmployeeInfoDtoImplCopyWithImpl(
    _$EmployeeInfoDtoImpl _value,
    $Res Function(_$EmployeeInfoDtoImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of EmployeeInfoDto
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? department = freezed,
    Object? position = freezed,
    Object? status = null,
    Object? phone = null,
    Object? hireDate = freezed,
    Object? head = null,
  }) {
    return _then(
      _$EmployeeInfoDtoImpl(
        department: freezed == department
            ? _value.department
            : department // ignore: cast_nullable_to_non_nullable
                  as String?,
        position: freezed == position
            ? _value.position
            : position // ignore: cast_nullable_to_non_nullable
                  as String?,
        status: null == status
            ? _value.status
            : status // ignore: cast_nullable_to_non_nullable
                  as String,
        phone: null == phone
            ? _value.phone
            : phone // ignore: cast_nullable_to_non_nullable
                  as String,
        hireDate: freezed == hireDate
            ? _value.hireDate
            : hireDate // ignore: cast_nullable_to_non_nullable
                  as String?,
        head: null == head
            ? _value.head
            : head // ignore: cast_nullable_to_non_nullable
                  as bool,
      ),
    );
  }
}

/// @nodoc
@JsonSerializable()
class _$EmployeeInfoDtoImpl implements _EmployeeInfoDto {
  const _$EmployeeInfoDtoImpl({
    this.department,
    this.position,
    required this.status,
    required this.phone,
    @JsonKey(name: 'hire_date') this.hireDate,
    required this.head,
  });

  factory _$EmployeeInfoDtoImpl.fromJson(Map<String, dynamic> json) =>
      _$$EmployeeInfoDtoImplFromJson(json);

  @override
  final String? department;
  @override
  final String? position;
  @override
  final String status;
  @override
  final String phone;
  @override
  @JsonKey(name: 'hire_date')
  final String? hireDate;
  @override
  final bool head;

  @override
  String toString() {
    return 'EmployeeInfoDto(department: $department, position: $position, status: $status, phone: $phone, hireDate: $hireDate, head: $head)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$EmployeeInfoDtoImpl &&
            (identical(other.department, department) ||
                other.department == department) &&
            (identical(other.position, position) ||
                other.position == position) &&
            (identical(other.status, status) || other.status == status) &&
            (identical(other.phone, phone) || other.phone == phone) &&
            (identical(other.hireDate, hireDate) ||
                other.hireDate == hireDate) &&
            (identical(other.head, head) || other.head == head));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
    runtimeType,
    department,
    position,
    status,
    phone,
    hireDate,
    head,
  );

  /// Create a copy of EmployeeInfoDto
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$EmployeeInfoDtoImplCopyWith<_$EmployeeInfoDtoImpl> get copyWith =>
      __$$EmployeeInfoDtoImplCopyWithImpl<_$EmployeeInfoDtoImpl>(
        this,
        _$identity,
      );

  @override
  Map<String, dynamic> toJson() {
    return _$$EmployeeInfoDtoImplToJson(this);
  }
}

abstract class _EmployeeInfoDto implements EmployeeInfoDto {
  const factory _EmployeeInfoDto({
    final String? department,
    final String? position,
    required final String status,
    required final String phone,
    @JsonKey(name: 'hire_date') final String? hireDate,
    required final bool head,
  }) = _$EmployeeInfoDtoImpl;

  factory _EmployeeInfoDto.fromJson(Map<String, dynamic> json) =
      _$EmployeeInfoDtoImpl.fromJson;

  @override
  String? get department;
  @override
  String? get position;
  @override
  String get status;
  @override
  String get phone;
  @override
  @JsonKey(name: 'hire_date')
  String? get hireDate;
  @override
  bool get head;

  /// Create a copy of EmployeeInfoDto
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$EmployeeInfoDtoImplCopyWith<_$EmployeeInfoDtoImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

ProfileDto _$ProfileDtoFromJson(Map<String, dynamic> json) {
  return _ProfileDto.fromJson(json);
}

/// @nodoc
mixin _$ProfileDto {
  int get id => throw _privateConstructorUsedError;
  String get username => throw _privateConstructorUsedError;
  @JsonKey(name: 'full_name')
  String get fullName => throw _privateConstructorUsedError;
  String get role => throw _privateConstructorUsedError;
  String get email => throw _privateConstructorUsedError;
  String? get avatar => throw _privateConstructorUsedError;
  EmployeeInfoDto? get employee => throw _privateConstructorUsedError;

  /// Serializes this ProfileDto to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ProfileDto
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ProfileDtoCopyWith<ProfileDto> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ProfileDtoCopyWith<$Res> {
  factory $ProfileDtoCopyWith(
    ProfileDto value,
    $Res Function(ProfileDto) then,
  ) = _$ProfileDtoCopyWithImpl<$Res, ProfileDto>;
  @useResult
  $Res call({
    int id,
    String username,
    @JsonKey(name: 'full_name') String fullName,
    String role,
    String email,
    String? avatar,
    EmployeeInfoDto? employee,
  });

  $EmployeeInfoDtoCopyWith<$Res>? get employee;
}

/// @nodoc
class _$ProfileDtoCopyWithImpl<$Res, $Val extends ProfileDto>
    implements $ProfileDtoCopyWith<$Res> {
  _$ProfileDtoCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ProfileDto
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? username = null,
    Object? fullName = null,
    Object? role = null,
    Object? email = null,
    Object? avatar = freezed,
    Object? employee = freezed,
  }) {
    return _then(
      _value.copyWith(
            id: null == id
                ? _value.id
                : id // ignore: cast_nullable_to_non_nullable
                      as int,
            username: null == username
                ? _value.username
                : username // ignore: cast_nullable_to_non_nullable
                      as String,
            fullName: null == fullName
                ? _value.fullName
                : fullName // ignore: cast_nullable_to_non_nullable
                      as String,
            role: null == role
                ? _value.role
                : role // ignore: cast_nullable_to_non_nullable
                      as String,
            email: null == email
                ? _value.email
                : email // ignore: cast_nullable_to_non_nullable
                      as String,
            avatar: freezed == avatar
                ? _value.avatar
                : avatar // ignore: cast_nullable_to_non_nullable
                      as String?,
            employee: freezed == employee
                ? _value.employee
                : employee // ignore: cast_nullable_to_non_nullable
                      as EmployeeInfoDto?,
          )
          as $Val,
    );
  }

  /// Create a copy of ProfileDto
  /// with the given fields replaced by the non-null parameter values.
  @override
  @pragma('vm:prefer-inline')
  $EmployeeInfoDtoCopyWith<$Res>? get employee {
    if (_value.employee == null) {
      return null;
    }

    return $EmployeeInfoDtoCopyWith<$Res>(_value.employee!, (value) {
      return _then(_value.copyWith(employee: value) as $Val);
    });
  }
}

/// @nodoc
abstract class _$$ProfileDtoImplCopyWith<$Res>
    implements $ProfileDtoCopyWith<$Res> {
  factory _$$ProfileDtoImplCopyWith(
    _$ProfileDtoImpl value,
    $Res Function(_$ProfileDtoImpl) then,
  ) = __$$ProfileDtoImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({
    int id,
    String username,
    @JsonKey(name: 'full_name') String fullName,
    String role,
    String email,
    String? avatar,
    EmployeeInfoDto? employee,
  });

  @override
  $EmployeeInfoDtoCopyWith<$Res>? get employee;
}

/// @nodoc
class __$$ProfileDtoImplCopyWithImpl<$Res>
    extends _$ProfileDtoCopyWithImpl<$Res, _$ProfileDtoImpl>
    implements _$$ProfileDtoImplCopyWith<$Res> {
  __$$ProfileDtoImplCopyWithImpl(
    _$ProfileDtoImpl _value,
    $Res Function(_$ProfileDtoImpl) _then,
  ) : super(_value, _then);

  /// Create a copy of ProfileDto
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? username = null,
    Object? fullName = null,
    Object? role = null,
    Object? email = null,
    Object? avatar = freezed,
    Object? employee = freezed,
  }) {
    return _then(
      _$ProfileDtoImpl(
        id: null == id
            ? _value.id
            : id // ignore: cast_nullable_to_non_nullable
                  as int,
        username: null == username
            ? _value.username
            : username // ignore: cast_nullable_to_non_nullable
                  as String,
        fullName: null == fullName
            ? _value.fullName
            : fullName // ignore: cast_nullable_to_non_nullable
                  as String,
        role: null == role
            ? _value.role
            : role // ignore: cast_nullable_to_non_nullable
                  as String,
        email: null == email
            ? _value.email
            : email // ignore: cast_nullable_to_non_nullable
                  as String,
        avatar: freezed == avatar
            ? _value.avatar
            : avatar // ignore: cast_nullable_to_non_nullable
                  as String?,
        employee: freezed == employee
            ? _value.employee
            : employee // ignore: cast_nullable_to_non_nullable
                  as EmployeeInfoDto?,
      ),
    );
  }
}

/// @nodoc
@JsonSerializable()
class _$ProfileDtoImpl implements _ProfileDto {
  const _$ProfileDtoImpl({
    required this.id,
    required this.username,
    @JsonKey(name: 'full_name') required this.fullName,
    required this.role,
    required this.email,
    this.avatar,
    this.employee,
  });

  factory _$ProfileDtoImpl.fromJson(Map<String, dynamic> json) =>
      _$$ProfileDtoImplFromJson(json);

  @override
  final int id;
  @override
  final String username;
  @override
  @JsonKey(name: 'full_name')
  final String fullName;
  @override
  final String role;
  @override
  final String email;
  @override
  final String? avatar;
  @override
  final EmployeeInfoDto? employee;

  @override
  String toString() {
    return 'ProfileDto(id: $id, username: $username, fullName: $fullName, role: $role, email: $email, avatar: $avatar, employee: $employee)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ProfileDtoImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.username, username) ||
                other.username == username) &&
            (identical(other.fullName, fullName) ||
                other.fullName == fullName) &&
            (identical(other.role, role) || other.role == role) &&
            (identical(other.email, email) || other.email == email) &&
            (identical(other.avatar, avatar) || other.avatar == avatar) &&
            (identical(other.employee, employee) ||
                other.employee == employee));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
    runtimeType,
    id,
    username,
    fullName,
    role,
    email,
    avatar,
    employee,
  );

  /// Create a copy of ProfileDto
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ProfileDtoImplCopyWith<_$ProfileDtoImpl> get copyWith =>
      __$$ProfileDtoImplCopyWithImpl<_$ProfileDtoImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ProfileDtoImplToJson(this);
  }
}

abstract class _ProfileDto implements ProfileDto {
  const factory _ProfileDto({
    required final int id,
    required final String username,
    @JsonKey(name: 'full_name') required final String fullName,
    required final String role,
    required final String email,
    final String? avatar,
    final EmployeeInfoDto? employee,
  }) = _$ProfileDtoImpl;

  factory _ProfileDto.fromJson(Map<String, dynamic> json) =
      _$ProfileDtoImpl.fromJson;

  @override
  int get id;
  @override
  String get username;
  @override
  @JsonKey(name: 'full_name')
  String get fullName;
  @override
  String get role;
  @override
  String get email;
  @override
  String? get avatar;
  @override
  EmployeeInfoDto? get employee;

  /// Create a copy of ProfileDto
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ProfileDtoImplCopyWith<_$ProfileDtoImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
