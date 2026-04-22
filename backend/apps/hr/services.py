import logging

from django.db import transaction

from account.models import Employee
from hr.enbek_client import EnbekClient
from hr.models import Vacation, SickLeave, EmploymentContract

logger = logging.getLogger(__name__)


class EnbekSyncService:
    def __init__(self):
        self.client = EnbekClient()

    def sync_all(self):
        logger.info("sync_started")

        try:
            vacations = self.client.get_vacations() or []
            sick_leaves = self.client.get_sick_leaves() or []
            employment_contracts = self.client.get_employment_contracts() or []

            created = 0
            updated = 0

            with transaction.atomic():
                c, u = self._sync_vacations(vacations)
                created += c
                updated += u

                c, u = self._sync_sick_leaves(sick_leaves)
                created += c
                updated += u

                c, u = self._sync_employment_contracts(employment_contracts)
                created += c
                updated += u

            logger.info(
                "sync_completed",
                extra={
                    "created": created,
                    "updated": updated,
                    "vacations_count": len(vacations),
                    "sick_leaves_count": len(sick_leaves),
                    "employment_contracts_count": len(employment_contracts),
                }
            )

            return {
                "created": created,
                "updated": updated,
            }

        except Exception:
            logger.exception("sync_error")
            raise

    def _sync_vacations(self, items):
        created = 0
        updated = 0

        for item in items:
            enbek_id = self._get_enbek_id(item)
            if not enbek_id:
                continue

            _, is_created = Vacation.objects.update_or_create(
                enbek_id=enbek_id,
                defaults={
                    "employee": self._get_employee(item),
                    "type": self._get_value(item, "type", "vacation_type", "leave_type") or "",
                    "start_date": self._get_value(item, "start_date", "date_start"),
                    "end_date": self._get_value(item, "end_date", "date_end"),
                    "status": self._get_value(item, "status") or "",
                }
            )

            if is_created:
                created += 1
            else:
                updated += 1

        return created, updated

    def _sync_sick_leaves(self, items):
        created = 0
        updated = 0

        for item in items:
            enbek_id = self._get_enbek_id(item)
            if not enbek_id:
                continue

            _, is_created = SickLeave.objects.update_or_create(
                enbek_id=enbek_id,
                defaults={
                    "employee": self._get_employee(item),
                    "start_date": self._get_value(item, "start_date", "date_start"),
                    "end_date": self._get_value(item, "end_date", "date_end"),
                    "document_number": self._get_value(item, "document_number", "number", "doc_number"),
                }
            )

            if is_created:
                created += 1
            else:
                updated += 1

        return created, updated

    def _sync_employment_contracts(self, items):
        created = 0
        updated = 0

        for item in items:
            enbek_id = self._get_enbek_id(item)
            if not enbek_id:
                continue

            _, is_created = EmploymentContract.objects.update_or_create(
                enbek_id=enbek_id,
                defaults={
                    "employee": self._get_employee(item),
                    "number": self._get_value(item, "number", "contract_number"),
                    "date": self._get_value(item, "date", "contract_date"),
                    "type": self._get_value(item, "type", "contract_type") or "",
                    "status": self._get_value(item, "status") or "",
                }
            )

            if is_created:
                created += 1
            else:
                updated += 1

        return created, updated

    def _get_employee(self, item):
        iin = self._get_value(item, "iin", "employee_iin", "person_iin")
        if not iin:
            return None
        return Employee.objects.filter(iin=iin).first()

    def _get_enbek_id(self, item):
        return self._get_value(item, "enbek_id", "id", "external_id")

    @staticmethod
    def _get_value(data, *keys):
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return value
        return None