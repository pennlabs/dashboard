from django.contrib import admin

from .models import Deployment, DeploymentEvent, Product, ReplicaSetSnapshot

admin.site.register(Product)
admin.site.register(Deployment)
admin.site.register(DeploymentEvent)
admin.site.register(ReplicaSetSnapshot)
