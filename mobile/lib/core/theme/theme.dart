import 'package:flutter/material.dart';
import 'metrix_colors.dart';
import 'metrix_tokens.dart';

class MetrixTheme {
  MetrixTheme._();

  static ThemeData light() {
    final baseTextTheme = ThemeData.light().textTheme.apply(
      fontFamily: 'Inter',
      bodyColor: MetrixColors.text,
      displayColor: MetrixColors.text,
    );

    final textTheme = baseTextTheme.copyWith(
      titleLarge: const TextStyle(
        fontFamily: 'Inter',
        fontSize: 24, // 1.5rem
        fontWeight: FontWeight.w700,
        color: MetrixColors.text,
      ),
      bodyMedium: const TextStyle(
        fontFamily: 'Inter',
        color: MetrixColors.text,
      ),
      bodySmall: const TextStyle(
        fontFamily: 'Inter',
        color: MetrixColors.textMuted,
      ),
    );

    return ThemeData(
      useMaterial3: true,
      fontFamily: 'Inter',
      scaffoldBackgroundColor: MetrixColors.surfaceMuted,
      colorScheme: ColorScheme.fromSeed(
        seedColor: MetrixColors.primary,
        primary: MetrixColors.primary,
        secondary: MetrixColors.accent,
        error: MetrixColors.danger,
        surface: MetrixColors.surface,
        brightness: Brightness.light,
      ),
      textTheme: textTheme,

      // .bpm-filter-card / .bpm-table-card
      cardTheme: CardThemeData(
        color: MetrixColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(MetrixRadius.md),
          side: const BorderSide(color: MetrixColors.border),
        ),
      ),

      // .bpm-btn--primary
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: MetrixColors.primary,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(MetrixRadius.sm),
          ),
          textStyle: const TextStyle(
            fontFamily: 'Inter',
            fontWeight: FontWeight.w500,
          ),
        ).copyWith(
          backgroundColor: WidgetStateProperty.resolveWith((states) {
            if (states.contains(WidgetState.pressed)) {
              return MetrixColors.primaryHover;
            }
            return MetrixColors.primary;
          }),
        ),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: MetrixColors.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(MetrixRadius.sm),
          borderSide: const BorderSide(color: MetrixColors.border),
        ),
      ),
    );
  }
}