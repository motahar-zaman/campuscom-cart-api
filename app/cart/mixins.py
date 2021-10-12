from datetime import datetime
from decouple import config
import pytz


class ResponseFormaterMixin(object):
    def format_data(self, data, many=False):
        resp = {
            'url': config('API_URL', '') + self.request.get_full_path(),
            'date_time': datetime.now().replace(tzinfo=pytz.utc),
            'success': True,
        }

        if many:
            resp['total'] = len(data)

        resp['data'] = data
        return resp

    def object_decorator(self, obj):
        return self.format_data(obj)

    def list_decorator(self, obj_list):
        return self.format_data(obj_list, many=True)
