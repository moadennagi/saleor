import logging
import requests

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import MiddlewareNotUsed
from django.utils import timezone
from django.utils.functional import SimpleLazyObject
from django.utils.translation import get_language
from django_countries.fields import Country
from graphql_jwt.utils import jwt_decode

from ..account.utils import decode_jwt_token
from ..discount.utils import fetch_discounts, fetch_customer, deactivate_all_discounts, activate_user_discounts
from ..plugins.manager import get_plugins_manager
from . import analytics
from .utils import get_client_ip, get_country_by_ip, get_currency_for_country

logger = logging.getLogger(__name__)


def google_analytics(get_response):
    """Report a page view to Google Analytics."""

    if not settings.GOOGLE_ANALYTICS_TRACKING_ID:
        raise MiddlewareNotUsed()

    def _google_analytics_middleware(request):
        client_id = analytics.get_client_id(request)
        path = request.path
        language = get_language()
        headers = request.META
        try:
            analytics.report_view(
                client_id, path=path, language=language, headers=headers
            )
        except Exception:
            logger.exception("Unable to update analytics")
        return get_response(request)

    return _google_analytics_middleware


def request_time(get_response):
    def _stamp_request(request):
        request.request_time = timezone.now()
        return get_response(request)

    return _stamp_request


def discounts(get_response):
    """Assign active discounts to `request.discounts`.

        Only current user' sales are active
    """

    def _discounts_middleware(request):
        user = None
        auth_header = request.headers.get('Authorization')
        if auth_header:
            auth = auth_header.split(' ')
            prefix = 'JWT'
            if len(auth) == 2 and auth[0].lower() == prefix.lower():
                token = auth[1]
                decoded = jwt_decode(token)
                email = decoded.get('email')
                # send user info to foodelux - get company
                response = requests.post('http://192.168.1.112:8080/users/company/', json=decoded)
                
                if response.status_code == 200:
                    response_json = response.json()
                    company = response_json.get('email')
                    user = fetch_customer(company)

        deactivate_all_discounts(request.request_time)
        activate_user_discounts(user)

        request.discounts = SimpleLazyObject(
            lambda: fetch_discounts(request.request_time, user)
        )
        return get_response(request)

    return _discounts_middleware


def country(get_response):
    """Detect the user's country and assign it to `request.country`."""

    def _country_middleware(request):
        client_ip = get_client_ip(request)
        if client_ip:
            request.country = get_country_by_ip(client_ip)
        if not request.country:
            request.country = Country(settings.DEFAULT_COUNTRY)
        return get_response(request)

    return _country_middleware


def currency(get_response):
    """Take a country and assign a matching currency to `request.currency`."""

    def _currency_middleware(request):
        if hasattr(request, "country") and request.country is not None:
            request.currency = get_currency_for_country(request.country)
        else:
            request.currency = settings.DEFAULT_CURRENCY
        return get_response(request)

    return _currency_middleware


def site(get_response):
    """Clear the Sites cache and assign the current site to `request.site`.

    By default django.contrib.sites caches Site instances at the module
    level. This leads to problems when updating Site instances, as it's
    required to restart all application servers in order to invalidate
    the cache. Using this middleware solves this problem.
    """

    def _get_site():
        Site.objects.clear_cache()
        return Site.objects.get_current()

    def _site_middleware(request):
        request.site = SimpleLazyObject(_get_site)
        return get_response(request)

    return _site_middleware


def plugins(get_response):
    """Assign plugins manager."""

    def _get_manager():
        return get_plugins_manager(plugins=settings.PLUGINS)

    def _plugins_middleware(request):
        request.plugins = SimpleLazyObject(lambda: _get_manager())
        return get_response(request)

    return _plugins_middleware
