import 'package:flutter/material.dart';
import '../../core/theme/metrix_colors.dart';
import '../../core/theme/metrix_tokens.dart';

class AppTextField extends StatefulWidget {
  final TextEditingController controller;
  final String label;
  final bool obscureText;
  final IconData? icon;
  final String? Function(String?)? validator;
  final bool autocorrect;
  final bool enableSuggestions;
  final TextCapitalization textCapitalization;
  final TextInputType? keyboardType;
  final Iterable<String>? autofillHints;

  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    this.obscureText = false,
    this.icon,
    this.validator,
    this.autocorrect = true,
    this.enableSuggestions = true,
    this.textCapitalization = TextCapitalization.none,
    this.keyboardType,
    this.autofillHints,
  });

  @override
  State<AppTextField> createState() => _AppTextFieldState();
}

class _AppTextFieldState extends State<AppTextField> {
  late bool _obscured = widget.obscureText;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: widget.controller,
      obscureText: _obscured,
      validator: widget.validator,
      autocorrect: widget.obscureText ? false : widget.autocorrect,
      enableSuggestions: widget.obscureText ? false : widget.enableSuggestions,
      textCapitalization: widget.textCapitalization,
      keyboardType: widget.keyboardType,
      autofillHints: widget.autofillHints,
      style: const TextStyle(fontFamily: 'Inter', fontSize: 15),
      decoration: InputDecoration(
        labelText: widget.label,
        prefixIcon: widget.icon != null ? Icon(widget.icon, size: 20, color: MetrixColors.textMuted) : null,
        suffixIcon: widget.obscureText
            ? IconButton(
                icon: Icon(
                  _obscured ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                  size: 20,
                  color: MetrixColors.textMuted,
                ),
                tooltip: _obscured ? 'Показать пароль' : 'Скрыть пароль',
                onPressed: () => setState(() => _obscured = !_obscured),
              )
            : null,
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