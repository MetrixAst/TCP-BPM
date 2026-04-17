import csv

class OrgChart:
    DEFAULT_IMAGE = '/static/site/img/profile/profile-1.webp'

    def get_data(self, request, all_departments=True):
        from account.models import Employee, Department
        
        res = [['id', 'imageUrl', 'area', 'profileUrl', 'office', 'tags', 'isLoggedUser', 'positionName', 'name', 'parentId', 'size']]

        roots = Department.objects.filter(parent=None)

        if not roots.exists():
            return res

        for start_node in roots:
            nodes = start_node.get_descendants(include_self=True)

            for dept in nodes:
                dept_id = f"dept_{dept.id}"
                parent_id = f"dept_{dept.parent.id}" if dept.parent else ""
                
                res.append([
                    dept_id,
                    self.DEFAULT_IMAGE,
                    'Департамент',
                    '#',
                    str(dept.name),
                    'dept,infinity',
                    'false',
                    'Отдел',
                    str(dept.name),
                    parent_id,
                    ''
                ])

                active_employees = dept.employees.filter(status='active')
                
                for emp in active_employees:
                    emp_id = f"emp_{emp.id}"
                    
                    try:
                        image = emp.user.get_avatar_url() if emp.user else self.DEFAULT_IMAGE
                    except:
                        image = self.DEFAULT_IMAGE

                    full_name = "Сотрудник"
                    if emp.user:
                        full_name = emp.user.get_full_name() or emp.user.username

                    res.append([
                        emp_id,
                        image,
                        'Сотрудник',
                        '#',
                        str(dept.name),
                        'сотрудник,infinity',
                        'true' if (emp.user and emp.user == request.user) else 'false',
                        str(emp.position.title) if emp.position else "Сотрудник",
                        full_name,
                        dept_id,
                        ''
                    ])

        return res

    def write_response_data(self, response, data):
        writer = csv.writer(response)
        for current in data:
            writer.writerow(current)