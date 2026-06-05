from django.core.paginator import Paginator

LIST_PAGE_SIZE = 15


def page_from_request(request, default=1):
    try:
        return max(1, int(request.GET.get('page', default)))
    except (TypeError, ValueError):
        return default


class CustomPaginator:

    def __init__(self, queryset, page, itemsPerPage=LIST_PAGE_SIZE):
        self.queryset = queryset

        paginator = Paginator(queryset, itemsPerPage)
        if paginator.num_pages < page:
            page = 1

        self.current = page
        self.items = paginator.get_page(page)
        self.count = paginator.count
        self.pages_count = paginator.num_pages
        self.pages = paginator.get_elided_page_range(page, on_ends=0)