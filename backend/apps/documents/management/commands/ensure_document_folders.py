from django.core.management.base import BaseCommand

from documents.enums import DocumentTypeEnum
from documents.folder_structure import ensure_folder_tree


class Command(BaseCommand):
    help = 'Создаёт стандартные подпапки для документооборота и закупок'

    def handle(self, *args, **options):
        for document_type, _label in DocumentTypeEnum.list():
            root = ensure_folder_tree(document_type)
            count = root.get_descendants(include_self=False).count()
            self.stdout.write(
                self.style.SUCCESS(f'{document_type}: корень «{root.name}», подпапок: {count}')
            )
