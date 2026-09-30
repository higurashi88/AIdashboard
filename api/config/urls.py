from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from apps.core.views import healthz


class PublicSchemaView(SpectacularAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class PublicSwaggerView(SpectacularSwaggerView):
    authentication_classes = []
    permission_classes = [AllowAny]


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/healthz/", healthz, name="healthz"),
    path("api/v1/", include("apps.core.api.urls")),
    path("api/schema/", PublicSchemaView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        PublicSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
