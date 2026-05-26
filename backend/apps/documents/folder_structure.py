"""Стандартные подпапки для документооборота и закупок."""

from __future__ import annotations

from typing import Iterable

from .enums import DocumentTypeEnum

# Имена глобально уникальны (ограничение модели Folder.name).
_FOLDER_SPECS: dict[str, list[str]] = {
    DocumentTypeEnum.DOCUMENTS.value[0]: [
        'Документооборот / Входящие',
        'Документооборот / Исходящие',
        'Документооборот / Приказы и распоряжения',
        'Документооборот / Архив',
    ],
    DocumentTypeEnum.PURCHASES.value[0]: [
        'Закупки / Заявки на закупку',
        'Закупки / Тендерная документация',
        'Закупки / Договоры с поставщиками',
        'Закупки / Акты и закрывающие',
        'Закупки / Архив',
    ],
}

_ROOT_TITLES = {
    DocumentTypeEnum.DOCUMENTS.value[0]: 'Документооборот',
    DocumentTypeEnum.PURCHASES.value[0]: 'Закупки',
    DocumentTypeEnum.BUDGET.value[0]: 'Бюджет',
}


def _get_root_folder(document_type: str):
    from .models import Folder

    title = _ROOT_TITLES.get(document_type, document_type)
    root, _ = Folder.objects.get_or_create(
        root_type=document_type,
        defaults={'name': title},
    )
    return root


def ensure_folder_tree(document_type: str):
    """
    Создаёт подпапки под корнем типа, если их ещё нет.
    Возвращает корневую папку.
    """
    from .models import Folder

    root = _get_root_folder(document_type)
    names: Iterable[str] = _FOLDER_SPECS.get(document_type, ())
    for name in names:
        folder, created = Folder.objects.get_or_create(
            name=name,
            defaults={'parent': root},
        )
        if not created and folder.parent_id != root.id:
            folder.parent = root
            folder.save()
    return root


def folder_display_name(name: str) -> str:
    """Короткое имя для сайдбара: «Закупки / Заявки» → «Заявки»."""
    if ' / ' in name:
        return name.split(' / ', 1)[1]
    return name
