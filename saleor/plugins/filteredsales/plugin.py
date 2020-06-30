
import requests
from datetime import datetime
from urllib.parse import urlparse
from django.core.handlers.wsgi import WSGIRequest
from typing import List, Optional, Dict

from ..base_plugin import BasePlugin
from ...account.models import User
from ...discount.models import Sale

class FilterSales(BasePlugin):
    PLUGIN_ID = "foodelux.filtersales"
    PLUGIN_NAME = "Filter sales"
    DEFAULT_ACTIVE = True
    PLUGIN_DESCRIPTION = (
        "Filter sales according to the company that the customer belongs to, "
        "the company-customer information is handeled by Foodelux."
    )

    def _get_customer_parent(
        self,
        context: WSGIRequest,
        user: User
        ) -> User:
        """Get user info from foodelux.

        Sends a http request to foodelux, gets the user parent or None
        """
        customer = None
        if not user.is_anonymous:
            info = {'email': user.email}
            response = requests.post('http://192.168.1.112:8080/users/company/', json=info)
            if response.status_code == 200:
                email = response.json()['email']
                try:
                    customer = User.objects.get(email=email)
                except User.DoesNotExist as e:
                    print(e)

        return customer

    def preprocess_discounts(
        self,
        sales: Dict[datetime, Sale],
        context: WSGIRequest,
        user: Optional[User] = None
    ) -> List[Sale]:
        """Pre processes all the discounts.

        Overwite this method if you need to apply specific logic for the loading of discounts
        (discounts.loader)
        """
        result = {}
        referer = context.headers.get('Referer')
        domain = urlparse(referer).netloc
        # apply only if request is coming from store
        # FIXME: add store url to .env
        if domain == 'localhost:3000':
            if not user.is_anonymous:
                customer = self._get_customer_parent(context, user)
                if customer:
                    for dt, ss in sales.items():
                        result = {s.pk for s in ss if s.customer if s.customer.pk == customer.id}
            return result  
        return sales