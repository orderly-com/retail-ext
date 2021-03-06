
import datetime

from typing import Any, List, Tuple, Optional, Dict
from dateutil.relativedelta import relativedelta

from django.db.models import Subquery, Count, Min, Sum, Max, F
from django.db.models.expressions import OuterRef
from django.db.models.fields import IntegerField
from django.db.models.query import Q
from django.db.models import QuerySet
from django.contrib.postgres.aggregates import ArrayAgg

from team.models import OrderProduct

from core.utils import list_to_dict
from client_filter.conditions import (
    RangeCondition, BooleanCondition, DateRangeCondition, SelectCondition
)

from .models import PurchaseBase

# RFM Filters
class RFMScoreR(RangeCondition):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.range(0, 5)
        self.config(postfix=' 分', max_postfix=' +')

    def filter(self, client_qs: QuerySet, rfm_r_range: Any) -> Tuple[QuerySet, Q]:
        q = Q()

        q &= Q(rfm_recency__range=rfm_r_range)

        return client_qs, q


class RFMScoreF(RangeCondition):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.range(0, 5)
        self.config(postfix=' 分', max_postfix=' +')

    def filter(self, client_qs: QuerySet, rfm_f_range: Any) -> Tuple[QuerySet, Q]:
        q = Q()

        q &= Q(rfm_recency__range=rfm_f_range)

        return client_qs, q


class RFMScoreM(RangeCondition):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.range(0, 5)
        self.config(postfix=' 分', max_postfix=' +')

    def filter(self, client_qs: QuerySet, rfm_m_range: Any) -> Tuple[QuerySet, Q]:
        q = Q()

        q &= Q(rfm_recency__range=rfm_m_range)

        return client_qs, q


# Purchase Behavior Filters
class PurchaseCount(RangeCondition):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_options(datetime_range=DateRangeCondition('時間區間'))
        self.range(0, 15)
        self.config(postfix=' 次', max_postfix=' +')

    def filter(self, client_qs: QuerySet, purchase_count_range: Any) -> Tuple[QuerySet, Q]:
        q = Q()

        datetime_range = self.options.get('datetime_range')
        orderbase_qs = PurchaseBase.objects.filter(clientbase_id=OuterRef('id'), datetime__range=datetime_range)
        client_qs = client_qs.annotate(purchase_count=Subquery(orderbase_qs.annotate(count=Count('external_id')).values('count')[:1], output_field=IntegerField()))

        q &= Q(purchase_count__range=purchase_count_range)

        return client_qs, q


class PurchaseAmount(RangeCondition):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_options(datetime_range=DateRangeCondition('時間區間'))
        self.range(0, 15)
        self.config(prefix='$ ', postfix=' 元', max_postfix=' +')

    def filter(self, client_qs: QuerySet, purchase_amount_range: Any) -> Tuple[QuerySet, Q]:
        q = Q()

        datetime_range = self.options.get('datetime_range')
        orderbase_qs = PurchaseBase.objects.filter(clientbase_id=OuterRef('id'), datetime__range=datetime_range)
        client_qs = client_qs.annotate(purchase_amount=Subquery(orderbase_qs.annotate(amount=Sum('total_price')).values('amount')[:1], output_field=IntegerField()))

        q &= Q(purchase_amount__range=purchase_amount_range)

        return client_qs, q


class ProductCategoryCondition(SelectCondition):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def filter(self, client_qs: QuerySet, category_ids: List[int]) -> Tuple[QuerySet, Q]:
        q = Q()

        intersection = self.options.get('intersection', False)
        if intersection:
            q &= Q(orderbase__orderproduct__productbase__category_ids__contains=category_ids)
        else:
            q &= Q(orderbase__orderproduct__productbase__category_ids__overlap=category_ids)

        return client_qs, q

    def real_time_init(self, team, *args, **kwargs):
        category_qs = team.productcategorybase_set.values('name', 'uuid')
        self.choice(*[{'text': item['name'], 'id': str(item['uuid'])} for item in category_qs])


class ProductCondition(SelectCondition):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def filter(self, client_qs: QuerySet, product_ids: List[int]) -> Tuple[QuerySet, Q]:
        q = Q()

        intersection = self.options.get('intersection', False)
        qs = (OrderProduct.objects.filter(clientbase_id__in=client_qs.values_list('id', flat=True))
            .values('clientbase_id')
            .annotate(productbase_ids=ArrayAgg('productbase_id'))
            .values('clientbase_id', 'productbase_ids')
        )
        valid_ids = []
        for item in qs:
            if intersection:
                if set(product_ids).issubset(set(item['productbase_ids'])):
                    valid_ids.append(item['clientbase_id'])
            else:
                if set(product_ids).intersection(set(item['productbase_ids'])):
                    valid_ids.append(item['clientbase_id'])

        q &= Q(id__in=valid_ids)

        return client_qs, q

    def real_time_init(self, team, *args, **kwargs):
        product_qs = team.productbase_set.filter(removed=False).values('name', 'uuid')
        self.choice(*[{'text': item['name'], 'id': str(item['uuid'])} for item in product_qs])

