import 'package:flutter/material.dart';
import '../../core/theme/metrix_colors.dart';
import '../../core/theme/metrix_tokens.dart';

class AppTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final bool obscureText;
  final IconData? icon;
  final String? Function(String?)? validator;

  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    this.obscureText = false,
    this.icon,
    this.validator,
  });

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      obscureText: obscureText,
      validator: validator,
      style: const TextStyle(fontFamily: 'Inter', fontSize: 15),
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: icon != null ? Icon(icon, size: 20, color: MetrixColors.textMuted) : null,
        filled: true,
        fillColor: MetrixColors.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(MetrixRadius.sm),
          borderSide: const BorderSide(color: MetrixColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(MetrixRadius.sm),
          borderSide: const BorderSide(color: MetrixColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(MetrixRadius.sm),
          borderSide: const BorderSide(color: MetrixColors.primary, width: 1.5),
        ),
      ),
    );
  }
}