from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^change_permissions/?', views.change_permissions),
    url(r'^delete_user/?', views.delete_user),
    url(r'^change_isactive/?', views.change_isactive),
    url(r'^add_dataset/?', views.add_dataset),
    url(r'^delete_dataset/?', views.delete_dataset),
    url(r'^open_close_dataset/?', views.open_close_dataset),
    url(r'^get_mappings/?', views.get_mappings),
    url(r'^add_script_project/?', views.add_script_project)
]
