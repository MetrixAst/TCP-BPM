import csv
import random

class OrgChart:
    images = [
        '/static/site/img/profile/profile-1.webp',
        '/static/site/img/profile/profile-2.webp',
        '/static/site/img/profile/profile-3.webp',
        '/static/site/img/profile/profile-4.webp',
        '/static/site/img/profile/profile-5.webp',
        '/static/site/img/profile/profile-6.webp',
        '/static/site/img/profile/profile-7.webp',
        '/static/site/img/profile/profile-8.webp',
        '/static/site/img/profile/profile-9.webp',
        '/static/site/img/profile/profile-10.webp',
        '/static/site/img/profile/profile-11.webp',
    ]

    def _get_random_name(self):
        
        names = ['Тумарбек', 'Аманжол', 'Ергали', 'Саша', 'Николай', 'Дмитрий', 'Асхат', 'Алмаз', 'Нурсултан', 'Олжас', 'Айбек', 'Рустем',]
        lastnames = ['Асылов', 'Кайрбеков', 'Александров', 'Яшин', 'Батырбеков', 'Батырханов', 'Ильин', 'Астахов', 'Махамбетов', 'Валиханов', 'Турсынов', 'Рысбаев',]

        return random.choice(names) + " " + random.choice(lastnames)


    def _get_random_job(self):
        
        jobs = ['Менеджер', 'Администратор', 'Охранник', 'Дизайнер', 'Консультант', 'Стажер', 'Помощник', 'Визуализатор', 'Маркетолог', 'Курьер', 'Водитель', 'Юрист',]

        return random.choice(jobs)



    def get_data(self, request, all = False):
        res = []
        res.append(['name','imageUrl','area','profileUrl','office','tags','isLoggedUser','positionName','id','parentId','size'])

        res.append(['Дима Низанов', self.images[1], 'Сотрудник', '#', 'Продажа', 'сотрудник,infinity', 'false', 'Руководитель', 1, '', ''])
        

        for user_id in range(2, 150):

            parent_id = ''
            if user_id < 4:
                parent_id = 1
            else:
                parent_id = random.randint(2, user_id - 1)

            res.append([self._get_random_name(), random.choice(self.images), self._get_random_job(), '#', 'Продажа', 'сотрудник,infinity', 'false', self._get_random_job(), user_id, parent_id, ''])

        return res
    

    def write_response_data(self, response, data):

        writer = csv.writer(response)

        for current in data:
            writer.writerow(current)
