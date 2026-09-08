class RoundItemAnswer {
  final int itemId;
  final bool passed;
  final String comment;
  final String? photoPath;

  const RoundItemAnswer({
    required this.itemId,
    required this.passed,
    this.comment = '',
    this.photoPath,
  });
}
