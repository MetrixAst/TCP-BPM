from hr.utils import OrgChart

def get_structure_data(request, all_departments=True):
    chart = OrgChart()
    return chart.get_data(request, all_departments=all_departments)