from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from apps.api import router
from apps.users.serializers import TenantTokenObtainPairView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Auth endpoints
    path('api/v1/auth/login/', TenantTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Resource endpoints
    path('api/v1/', include(router.urls)),
    path('api/v1/engine/', include('apps.ai_engine.urls')),
]
