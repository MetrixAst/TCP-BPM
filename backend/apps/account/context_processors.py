import json

from .i18n import DEFAULT_LANG
from .role_permissions import MenuItem
from .models import Notification, NotificationIndicator


def info(request):

    res = dict()

    #MENU
    # path = request.path
    # res['active_menu'] = path.split('/')[1]

    res = {
        'static_version': '1.0.9'
    }

    
    res['indicators'] = NotificationIndicator.get_data(request.user)
    res['indicators_json'] = json.dumps(res['indicators'])

    current_lang = getattr(request, 'current_lang', DEFAULT_LANG)

    res['current_lang'] = current_lang
    res['html_lang'] = current_lang

    #ADDITIONAL
    if request.user.is_authenticated:
        #NOTIFICATIONS
        res['notifications'] = request.user.notifications.all()[:10]
        res['menu'] = MenuItem.generate_menu(request.user)

    #MOBILE
    res['is_mobile'] = request.headers.get('Mobile', None) is not None
    
    user_agent = request.headers.get('User-Agent', '')
    if user_agent == 'flutter_app':
        res['is_mobile'] = True

    # res['is_mobile'] = True

    return res