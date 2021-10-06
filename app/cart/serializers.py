from rest_framework import serializers
from shared_models.models import Store, StoreConfiguration

class StoreSerializer(serializers.ModelSerializer):

    class Meta:
        model = Store
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        store_configurations = StoreConfiguration.objects.filter(store=instance)
        data['configurations'] = []

        for store_config in store_configurations:
            config = {}

            config['entity_name'] = store_config.external_entity.entity_name
            config['entity_type'] = store_config.external_entity.entity_type
            config['config_value'] = store_config.config_value

            data['configurations'].append(config)

        return data
