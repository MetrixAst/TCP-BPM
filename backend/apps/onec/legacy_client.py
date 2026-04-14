import requests
from django.conf import settings
from datetime import date

from .models import Remnant
from .serializers import RemnantSerializer, InvoiceSerializer

class OnecClient:
    BASE_URL = settings.ONEC_URL
    ALTERNATE_URL = settings.ALTERNATE_ONEC_URL

    def start(self):
        self.retrive_services(True)

    def _make_request(self, path: str, alternate: bool = False):
        '''
            alternate = Подгрузка альтернативного URL
        '''
        url = f"{self.BASE_URL}{path}"
        if alternate:
            url = f"{self.ALTERNATE_URL}{path}"

        response = requests.get(url)

        if response.status_code == 200:
            return response.json()
        else:
            print("ERROR")

        return None

    def get_date(self, is_range = False, first_date_of_year = False):
        today_date = date.today()
        today = today_date.strftime("%d.%m.%Y")

        if is_range:
            if first_date_of_year:
                first_day_date = today_date.replace(day=1, month=1)
            else:
                first_day_date = today_date.replace(day=1)

            first_day = first_day_date.strftime("%d.%m.%Y")

            return (first_day, today)

        return today


    def retrive_remnants(self):
        date = self.get_date()

        res = self._make_request(f'Get_RemnantsOfWarehouses/{date}')

        if res is not None:
            serializer = RemnantSerializer(data=res, many=True)
            if serializer.is_valid():
                data = serializer.validated_data
                for current in serializer.validated_data:
                    obj, created = Remnant.objects.get_or_create(NomenclatureCode=current.get('NomenclatureCode'), StorehouseCode=current.get('StorehouseCode'))
                    obj.QuantityRemainder = current.get('QuantityRemainder', 0)
                    obj.Nomenclature = current.get('Nomenclature')
                    obj.Storehouse = current.get('Storehouse')

                    obj.save()

    
    def retrive_invoices(self, first_date_of_year = False):
        start, end = self.get_date(is_range=True, first_date_of_year=first_date_of_year)

        res = self._make_request(f'Get_CompanyAccount/BeginDate/{start}/EndDate/{end}')
        
        if res is not None:
            serializer = InvoiceSerializer(data=res, many=True)
            if serializer.is_valid():
                serializer.save()

    
    def retrive_services(self, first_date_of_year = False):
        start, end = '01.09.2022', '05.12.2022' #self.get_date(is_range=True, first_date_of_year=first_date_of_year)

        res = self._make_request(f'ServiceOperationForGetServiceOperation/BeginDate/{start}/EndDate/{end}', alternate=True)
        
        if res is not None:
            print(res)
            # serializer = InvoiceSerializer(data=res, many=True)
            # if serializer.is_valid():
            #     serializer.save()