from rest_framework.routers import DefaultRouter

from .views import ElectionViewSet

router = DefaultRouter()
router.register("", ElectionViewSet, basename="election")

urlpatterns = router.urls
