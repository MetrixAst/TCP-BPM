import 'package:flutter/material.dart';
import '../../../core/theme/metrix_colors.dart';

Color taskStatusColor(String colorKey) {
  switch (colorKey) {
    case 'info':
      return MetrixColors.primary;
    case 'danger':
      return MetrixColors.danger;
    case 'warning':
      return MetrixColors.warning;
    case 'success':
      return MetrixColors.accent;
    case 'neutral':
    default:
      return MetrixColors.textMuted;
  }
}