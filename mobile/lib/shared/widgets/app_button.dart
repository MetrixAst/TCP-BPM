import 'package:flutter/material.dart';
import '../../core/theme/metrix_colors.dart';
import '../../core/theme/metrix_tokens.dart';

enum AppButtonVariant { primary, secondary, danger }

class AppButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final IconData? icon;
  final AppButtonVariant variant;

  const AppButton({
    super.key,
    required this.label,
    this.onPressed,
    this.isLoading = false,
    this.icon,
    this.variant = AppButtonVariant.primary,
  });

  @override
  Widget build(BuildContext context) {
    final isDisabled = onPressed == null || isLoading;

    final Color bg;
    final Color fg;
    final Border? border;

    switch (variant) {
      case AppButtonVariant.primary:
        bg = isDisabled ? MetrixColors.border : MetrixColors.primary;
        fg = Colors.white;
        border = null;
      case AppButtonVariant.secondary:
        bg = Colors.white;
        fg = isDisabled ? MetrixColors.textMuted : MetrixColors.primary;
        border = Border.all(color: MetrixColors.border);
      case AppButtonVariant.danger:
        bg = isDisabled ? MetrixColors.border : MetrixColors.danger;
        fg = Colors.white;
        border = null;
    }

    return SizedBox(
      height: 52,
      child: Material(
        color: bg,
        borderRadius: BorderRadius.circular(MetrixRadius.sm),
        child: InkWell(
          borderRadius: BorderRadius.circular(MetrixRadius.sm),
          onTap: isDisabled ? null : onPressed,
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(MetrixRadius.sm),
              border: border,
            ),
            alignment: Alignment.center,
            child: isLoading
                ? SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2, color: fg),
            )
                : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon != null) ...[
                  Icon(icon, size: 18, color: fg),
                  const SizedBox(width: 8),
                ],
                Text(
                  label,
                  style: TextStyle(
                    color: fg,
                    fontWeight: FontWeight.w600,
                    fontSize: 15,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}