import 'dart:io';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/api_result.dart';
import '../../../core/theme/metrix_colors.dart';
import '../../../shared/spacing.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_text_field.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../data/tickets_repository.dart';
import '../data/ticket_enums.dart';

class CreateTicketScreen extends StatefulWidget {
  final String? prefilledRoom;

  const CreateTicketScreen({super.key, this.prefilledRoom});

  @override
  State<CreateTicketScreen> createState() => _CreateTicketScreenState();
}

class _CreateTicketScreenState extends State<CreateTicketScreen> {
  final _formKey = GlobalKey<FormState>();
  final _titleController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _roomController = TextEditingController();
  final ImagePicker _picker = ImagePicker();

  late final TicketsRepository _repository;

  TicketCategory? _selectedCategory;
  TicketPriority _selectedPriority = TicketPriority.medium;
  File? _photo;

  bool _isPickingPhoto = false;
  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _repository = TicketsRepository(dio: DioClient().dio);
    if (widget.prefilledRoom != null) {
      _roomController.text = widget.prefilledRoom!;
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    _roomController.dispose();
    super.dispose();
  }

  Future<void> _pickPhoto(ImageSource source) async {
    setState(() => _isPickingPhoto = true);

    try {
      final xFile = await _picker.pickImage(source: source, imageQuality: 80);
      if (xFile != null && mounted) {
        setState(() => _photo = File(xFile.path));
      }
    } finally {
      if (mounted) setState(() => _isPickingPhoto = false);
    }
  }

  void _showPhotoSourceSheet() {
    showModalBottomSheet(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt_outlined),
              title: const Text('Сделать фото'),
              onTap: () {
                Navigator.pop(context);
                _pickPhoto(ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Выбрать из галереи'),
              onTap: () {
                Navigator.pop(context);
                _pickPhoto(ImageSource.gallery);
              },
            ),
            if (_photo != null)
              ListTile(
                leading: const Icon(Icons.delete_outline, color: MetrixColors.danger),
                title: const Text('Удалить фото', style: TextStyle(color: MetrixColors.danger)),
                onTap: () {
                  Navigator.pop(context);
                  setState(() => _photo = null);
                },
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleSubmit() async {
    if (!_formKey.currentState!.validate()) return;

    if (_selectedCategory == null) {
      setState(() => _errorMessage = 'Выберите категорию');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final result = await _repository.createTicket(
      title: _titleController.text.trim(),
      description: _descriptionController.text.trim(),
      category: _selectedCategory!.value,
      priority: _selectedPriority.value,
      room: _roomController.text.trim(),
      photo: _photo,
    );

    if (!mounted) return;

    setState(() => _isSubmitting = false);

    switch (result) {
      case Success():
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Заявка создана')),
          );
          context.pop(true);
        }
      case Failure(:final message):
        setState(() => _errorMessage = message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: MetrixColors.surfaceMuted,
      appBar: const AppTopBar(title: 'Новая заявка'),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Категория', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: MetrixColors.textMuted)),
                    const SizedBox(height: AppSpacing.xs),
                    DropdownButtonFormField<TicketCategory>(
                      initialValue: _selectedCategory,
                      isExpanded: true,
                      decoration: InputDecoration(
                        hintText: 'Выберите категорию',
                        filled: true,
                        fillColor: MetrixColors.surfaceMuted,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: const BorderSide(color: MetrixColors.border),
                        ),
                      ),
                      items: TicketCategory.values
                          .map((c) => DropdownMenuItem(
                                value: c,
                                child: Text(c.label, overflow: TextOverflow.ellipsis),
                              ))
                          .toList(),
                      onChanged: (value) => setState(() => _selectedCategory = value),
                      validator: (value) => value == null ? 'Выберите категорию' : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    const Text('Приоритет', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: MetrixColors.textMuted)),
                    const SizedBox(height: AppSpacing.xs),
                    Wrap(
                      spacing: 8,
                      children: TicketPriority.values.map((priority) {
                        final selected = priority == _selectedPriority;
                        return ChoiceChip(
                          label: Text(priority.label),
                          selected: selected,
                          onSelected: (_) => setState(() => _selectedPriority = priority),
                          selectedColor: MetrixColors.primary.withValues(alpha: 0.12),
                          labelStyle: TextStyle(
                            color: selected ? MetrixColors.primary : MetrixColors.textMuted,
                            fontWeight: FontWeight.w600,
                            fontSize: 12.5,
                          ),
                          side: BorderSide(color: selected ? MetrixColors.primary : MetrixColors.border),
                          backgroundColor: MetrixColors.surfaceMuted,
                        );
                      }).toList(),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    AppTextField(
                      controller: _titleController,
                      label: 'Тема заявки',
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return 'Укажите тему';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    TextFormField(
                      controller: _descriptionController,
                      maxLines: 4,
                      style: const TextStyle(fontFamily: 'Inter', fontSize: 15),
                      decoration: InputDecoration(
                        labelText: 'Описание проблемы',
                        alignLabelWithHint: true,
                        filled: true,
                        fillColor: MetrixColors.surface,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: const BorderSide(color: MetrixColors.border),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: const BorderSide(color: MetrixColors.border),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: const BorderSide(color: MetrixColors.primary, width: 1.5),
                        ),
                      ),
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return 'Опишите проблему';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    AppTextField(
                      controller: _roomController,
                      label: 'Помещение (необязательно)',
                      icon: Icons.room_outlined,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              AppCard(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    if (_photo != null)
                      ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.file(_photo!, height: 180, width: double.infinity, fit: BoxFit.cover),
                      )
                    else
                      Container(
                        height: 100,
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: MetrixColors.surfaceMuted,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.image_outlined, size: 32, color: MetrixColors.textMuted),
                      ),
                    const SizedBox(height: AppSpacing.sm),
                    AppButton(
                      label: _photo == null ? 'Прикрепить фото' : 'Изменить фото',
                      variant: AppButtonVariant.secondary,
                      icon: Icons.camera_alt,
                      isLoading: _isPickingPhoto,
                      onPressed: _showPhotoSourceSheet,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              if (_errorMessage != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_errorMessage!, style: const TextStyle(color: MetrixColors.danger), textAlign: TextAlign.center),
                ),
              AppButton(
                label: 'Создать заявку',
                isLoading: _isSubmitting,
                onPressed: _handleSubmit,
              ),
            ],
          ),
        ),
      ),
    );
  }
}