import 'package:flutter/material.dart';
import '../../core/theme/metrix_colors.dart';
import '../../core/theme/metrix_tokens.dart';

class AppCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;

  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: MetrixColors.surface,
        borderRadius: BorderRadius.circular(MetrixRadius.md),
        border: Border.all(color: MetrixColors.border),
        boxShadow: MetrixShadows.card,
      ),
      child: child,
    );
  }
}