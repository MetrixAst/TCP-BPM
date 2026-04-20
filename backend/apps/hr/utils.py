import csv
from account.models import Department, Employee

try:
    from hr.models import Company
except ImportError:
    Company = None

class OrgChart:
    DEFAULT_IMAGE = '/static/site/img/profile/profile-1.webp'

    HEADERS = [
        'id', 'imageUrl', 'area', 'profileUrl',
        'office', 'tags', 'isLoggedUser',
        'positionName', 'name', 'parentId', 'size',
    ]

    VIRTUAL_ROOT_ID = 'root_org'

    def get_data(self, request, all_departments=True):
        rows = [self.HEADERS]
        companies = self._get_companies()

        if not companies:
            self._append_orphan_departments(rows, request)
            return rows

        use_virtual_root = companies.count() > 1

        if use_virtual_root:
            rows.append(self._virtual_root_row())

        for company in companies:
            company_node_id = f"company_{company.id}"
            parent_of_company = self.VIRTUAL_ROOT_ID if use_virtual_root else ''

            rows.append(self._company_row(company, company_node_id, parent_of_company))

            root_depts = Department.objects.filter(
                company=company, parent=None
            ).order_by('name')

            for root_dept in root_depts:
                for dept in root_dept.get_descendants(include_self=True):
                    dept_node_id = f"dept_{dept.id}"

                    if dept.parent_id:
                        parent_node_id = f"dept_{dept.parent_id}"
                    else:
                        parent_node_id = company_node_id

                    rows.append(
                        self._department_row(dept, dept_node_id, parent_node_id)
                    )

                    for emp in self._active_employees(dept):
                        rows.append(
                            self._employee_row(emp, dept, dept_node_id, request)
                        )

        return rows

    def write_response_data(self, response, data):
        writer = csv.writer(response)
        for row in data:
            writer.writerow(row)

    def _virtual_root_row(self):
        return [
            self.VIRTUAL_ROOT_ID,
            self.DEFAULT_IMAGE,
            '',
            '#',
            'Организация',
            'root,infinity',
            'false',
            '',
            'Организация',
            '',
            '',
        ]

    def _company_row(self, company, node_id, parent_node_id):
        return [
            node_id,
            self.DEFAULT_IMAGE,
            'Компания',
            '#',
            str(company.name),
            'company,infinity',
            'false',
            'Компания',
            str(company.name),
            parent_node_id,
            '',
        ]

    def _department_row(self, dept, node_id, parent_node_id):
        head_info = dept.get_head_info
        return [
            node_id,
            head_info.get('photo', self.DEFAULT_IMAGE),
            'Департамент',
            '#',
            str(dept.name),
            'dept,infinity',
            'false',
            head_info.get('job_title', 'Отдел'),
            str(dept.name),
            parent_node_id,
            '',
        ]

    def _employee_row(self, emp, dept, dept_node_id, request):
        try:
            image = emp.user.get_avatar_url() if emp.user else self.DEFAULT_IMAGE
        except Exception:
            image = self.DEFAULT_IMAGE

        full_name = 'Сотрудник'
        if emp.user:
            full_name = emp.user.get_full_name() or emp.user.username

        is_logged = (
            'true'
            if emp.user and request and emp.user == request.user
            else 'false'
        )

        position_title = emp.position.title if emp.position else 'Сотрудник'

        return [
            f"emp_{emp.id}",
            image,
            'Сотрудник',
            '#',
            str(dept.name),
            'сотрудник,infinity',
            is_logged,
            position_title,
            full_name,
            dept_node_id,
            '',
        ]

    def _get_companies(self):
        if Company is None:
            return []
        return Company.objects.all().order_by('name')

    def _active_employees(self, dept):
        return (
            dept.employees
            .filter(status='active')
            .select_related('user', 'position')
            .order_by('-head', 'user__last_name')
        )

    def _append_orphan_departments(self, rows, request):
        orphans = Department.objects.filter(parent=None, company=None)

        if orphans.count() > 1:
            rows.append(self._virtual_root_row())
            parent_of_orphan = self.VIRTUAL_ROOT_ID
        else:
            parent_of_orphan = ''

        for root in orphans:
            for dept in root.get_descendants(include_self=True):
                dept_node_id = f"dept_{dept.id}"
                if dept.parent_id:
                    parent_node_id = f"dept_{dept.parent_id}"
                else:
                    parent_node_id = parent_of_orphan
                rows.append(
                    self._department_row(dept, dept_node_id, parent_node_id)
                )
                for emp in self._active_employees(dept):
                    rows.append(
                        self._employee_row(emp, dept, dept_node_id, request)
                    )