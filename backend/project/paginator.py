from django.core.paginator import Paginator

class CustomPaginator:

    def __init__(self, queryset, page, itemsPerPage=25):
        self.queryset = queryset

        paginator = Paginator(queryset, itemsPerPage)
        if paginator.num_pages < page:
            page = 1

        self.current = page
        self.items = paginator.get_page(page)
        self.count = paginator.count
        self.pages_count = paginator.num_pages
        self.pages = paginator.get_elided_page_range(page, on_ends=0)