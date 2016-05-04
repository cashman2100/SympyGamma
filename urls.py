from django.conf.urls.defaults import *

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

import os.path
p = os.path.join(os.path.dirname(__file__), 'media/')

urlpatterns = patterns(
    '',
    (r'^$', 'app.views.index'),
    (r'^input/', 'app.views.input'),
    (r'^fast_input/', 'app.views.fast_input'),
    (r'^request/(?P<image_id>\w*)$', 'app.views.request'),
    (r'^user/(?P<uuid>[\w-]*)$', 'app.views.user_request'),
    (r'card/(?P<card_name>\w*)$', 'app.views.eval_card'),
    (r'card_info/(?P<card_name>\w*)$', 'app.views.get_card_info'),
    (r'card_full/(?P<card_name>\w*)$', 'app.views.get_card_full')
)

handler404 = 'app.views.view_404'
handler500 = 'app.views.view_500'
