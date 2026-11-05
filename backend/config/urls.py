"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.db import connection
from django.urls import include, path
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    connection.ensure_connection()
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("api/v1/health/", health_check, name="health"),
    path('admin/', admin.site.urls),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/organizations/", include("organizations.urls")),
    path("api/v1/polls/", include("polls.urls")),
    path("api/v1/surveys/", include("surveys.urls")),
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/elections/", include("elections.urls")),
]
