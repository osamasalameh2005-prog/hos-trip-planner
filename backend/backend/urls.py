from django.contrib import admin
from django.urls import path
from django.http import FileResponse
from django.conf import settings
from django.conf.urls.static import static
from pathlib import Path

from api.views import create_trip


def frontend(request):
    index_file = Path(settings.BASE_DIR) / "static" / "frontend" / "index.html"
    return FileResponse(open(index_file, "rb"))


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/trips/', create_trip),
    path('', frontend),
]

urlpatterns += static(
    settings.STATIC_URL,
    document_root=settings.BASE_DIR / "static"
)