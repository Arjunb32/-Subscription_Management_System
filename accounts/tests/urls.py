from django.urls import include, path
from rest_framework import generics, serializers

from accounts.permissions import CustomerOwnershipPermission, CustomerScopedQuerysetMixin, customer_for_write, owned_object_or_404
from .fixtures.models import OwnedRecord


class RecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnedRecord
        fields = ["id", "customer", "title", "parent"]
        extra_kwargs = {"customer": {"required": False}}

    def validate(self, attrs):
        view = self.context["view"]
        user = self.context["request"].user
        existing = self.instance.customer if self.instance else None
        attrs["customer"] = customer_for_write(
            user, attrs.get("customer", existing), allow_staff=view.allow_staff,
        )
        if attrs.get("parent"):
            owned_object_or_404(OwnedRecord.objects.all(), user,
                                pk=attrs["parent"].pk, allow_staff=view.allow_staff)
        return attrs


class RecordList(CustomerScopedQuerysetMixin, generics.ListCreateAPIView):
    queryset = OwnedRecord.objects.order_by("pk")
    serializer_class = RecordSerializer
    permission_classes = [CustomerOwnershipPermission]


class StaffRecordList(RecordList):
    allow_staff = True


class RecordDetail(CustomerScopedQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = OwnedRecord.objects.all()
    serializer_class = RecordSerializer
    permission_classes = [CustomerOwnershipPermission]


urlpatterns = [
    path("api/", include("accounts.urls")),
    path("test/records/", RecordList.as_view()),
    path("test/staff-records/", StaffRecordList.as_view()),
    path("test/records/<int:pk>/", RecordDetail.as_view()),
]
