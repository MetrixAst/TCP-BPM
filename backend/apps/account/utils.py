from .models import Department

def get_structure_data(request, all_departments = False):

    department = None
    if all_departments:
        departments = Department.objects.filter(parent=None)
        if departments.count() > 0:
            department = departments.first()
    else:
        department = request.user.get_info().department
    

    if department is None:
        return []

    res = []
    res.append(['name','imageUrl','area','profileUrl','office','tags','isLoggedUser','positionName','id','parentId','size'])

    root_setted = False
    for current in department.get_descendants(include_self=True):

        department_id = str(current.id)
        department_name = current.name
        info = current.get_head_info

        parent_id = ''
        if current.parent is not None and root_setted:
            parent_id = str(current.parent.id)

        res.append([info['name'], info['photo'], 'Сотрудник', '#', department_name, 'сотрудник,infinity', 'false', info['job_title'], department_id, parent_id, ''])
        root_setted = True

        for employee in current.employees.filter(head=False):
            id = f"emp{employee.id}"
            res.append([str(employee), employee.user.get_avatar_url(), 'Сотрудник', '#', department_name, 'сотрудник,infinity', 'false', employee.job_title, id, department_id, ''])



    
    return res