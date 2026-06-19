import json

from visier_platform_sdk import ApiClient
from visier_platform_sdk.exceptions import ApiException

_AUTH_SETTINGS = ['CookieAuth', 'ApiKeyAuth', 'OAuth2Auth', 'BearerAuth']


class PlanningEventsApi:
    """
    Temporary direct-HTTP implementation of the Planning Events API.

    TODO: Replace this entire class once visier_platform_sdk ships the
          PlanningEventsApi (endpoint: GET /v1alpha/planning/data/events/:eventId).
          Expected replacement:
              from visier_platform_sdk import PlanningEventsApi
    """

    def __init__(self, api_client: ApiClient):
        # TODO: Replace with SDK-native initialization, e.g.:
        #   self._sdk_api = SdkPlanningEventsApi(api_client)
        self._api_client = api_client

    def get_event(self, event_id: str) -> dict:
        """
        Retrieves a planning event by ID.

        TODO: Replace body with SDK call, e.g.:
            return self._sdk_api.get_event(event_id)
        """
        method, url, headers, body, post_params = self._api_client.param_serialize(
            method='GET',
            resource_path='/v1alpha/planning/data/events/{eventId}',
            path_params={'eventId': event_id},
            auth_settings=_AUTH_SETTINGS,
        )
        response = self._api_client.call_api(method, url, header_params=headers)
        response.read()
        if response.status >= 400:
            body = response.data.decode('utf-8') if response.data else None
            ApiException.from_response(http_resp=response, body=body, data=None)
        return json.loads(response.data)
