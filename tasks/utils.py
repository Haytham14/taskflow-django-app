from datetime import datetime, timedelta

from django.utils import timezone


def resolve_date_range(request):
    """Turn the ?range=/&start=/&end= query params into a concrete date span.

    Defaults to the current calendar week (Monday–Sunday) when no filter is
    supplied at all. Shared by the dashboard and the task board so both
    pages' date filters behave identically.
    """
    today = timezone.localdate()
    range_key = request.GET.get("range", "week")

    if range_key == "today":
        start_date = end_date = today
    elif range_key == "month":
        start_date = today.replace(day=1)
        end_date = today
    elif range_key == "custom":
        default_start = today - timedelta(days=today.weekday())
        try:
            start_date = datetime.strptime(request.GET.get("start", ""), "%Y-%m-%d").date()
        except ValueError:
            start_date = default_start
        try:
            end_date = datetime.strptime(request.GET.get("end", ""), "%Y-%m-%d").date()
        except ValueError:
            end_date = today
        if start_date > end_date:
            start_date, end_date = end_date, start_date
    else:
        range_key = "week"
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)

    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
    return range_key, start_date, end_date, start_dt, end_dt
