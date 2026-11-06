"""Thin wrapper around AWS Performance Insights for the production database.

Every Penn Labs product shares one Postgres instance, so when its CPU alarm fires
the question is which product and query caused it. Performance Insights samples
the database's active sessions once a second and keeps the history, so that can
be answered after the fact, without connecting to the database at all.

"Load" throughout means average active sessions: how many queries were running or
waiting at once. It is sampled, so it says what the database spent its time on,
not how many times a query ran.

This is the only file that talks to AWS, as `k8s_client` is for Kubernetes.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

# Short: this runs inside a gunicorn sync worker, which a request can't outlive.
TIMEOUT_SECONDS = 5

MAX_WINDOW = timedelta(days=14)

TOP_QUERIES = 10
TOP_USERS = 6
TOP_WAITS = 6

# The most members of a group Performance Insights returns. Every user's load is
# requested, not just the top few, because their sum is what shares are out of.
ALL_USERS = 25

# Graph resolution for a window of up to this long. Performance Insights only
# accepts certain periods, and these keep a graph to at most 360 points.
PERIODS = (
    (timedelta(hours=6), 60),
    (timedelta(days=1), 300),
    (MAX_WINDOW, 3600),
)


class InvalidWindow(ValueError):
    """Performance Insights can't answer for this time window."""


class PerformanceInsightsUnavailable(Exception):
    """AWS didn't answer, or this backend isn't allowed to ask it."""


@lru_cache(maxsize=1)
def _client() -> Any:
    return boto3.client(
        "pi",
        region_name=settings.PERFORMANCE_INSIGHTS_REGION,
        config=Config(
            connect_timeout=TIMEOUT_SECONDS,
            read_timeout=TIMEOUT_SECONDS,
            retries={"max_attempts": 1},
        ),
    )


def _call(operation: str, **kwargs: Any) -> dict[str, Any]:
    """Call Performance Insights for the production database."""
    try:
        return getattr(_client(), operation)(
            ServiceType="RDS",
            Identifier=settings.PERFORMANCE_INSIGHTS_RESOURCE_ID,
            **kwargs,
        )
    except ClientError as exc:
        # Asking for a time outside its retention, for instance.
        if exc.response["Error"]["Code"] == "InvalidArgumentException":
            raise InvalidWindow(exc.response["Error"].get("Message", "")) from exc
        raise PerformanceInsightsUnavailable(str(exc)) from exc
    except BotoCoreError as exc:
        raise PerformanceInsightsUnavailable(str(exc)) from exc


def _period_for(start: datetime, end: datetime) -> int:
    window = end - start
    for longest, period in PERIODS:
        if window <= longest:
            return period
    raise InvalidWindow(f"The window can't be longer than {MAX_WINDOW.days} days")


def _load_points(start: datetime, end: datetime, period: int) -> list[dict[str, Any]]:
    response = _call(
        "get_resource_metrics",
        MetricQueries=[{"Metric": "db.load.avg"}],
        StartTime=start,
        EndTime=end,
        PeriodInSeconds=period,
    )
    metrics = response.get("MetricList") or [{}]
    return [
        # A sample with no Value is a gap, which is not the same as zero load.
        {
            "time": point["Timestamp"].astimezone(timezone.utc).isoformat(),
            "load": point.get("Value"),
        }
        for point in metrics[0].get("DataPoints", [])
    ]


def _top(
    group: str, limit: int, start: datetime, end: datetime, period: int
) -> list[dict[str, Any]]:
    """The members of a dimension group that added the most load, heaviest first."""
    response = _call(
        "describe_dimension_keys",
        Metric="db.load.avg",
        GroupBy={"Group": group, "Limit": limit},
        StartTime=start,
        EndTime=end,
        PeriodInSeconds=period,
    )
    return [
        {"load": key.get("Total", 0.0), "dimensions": key.get("Dimensions", {})}
        for key in response.get("Keys", [])
    ]


def get_insights(start: datetime, end: datetime) -> dict[str, Any]:
    """What the database was doing between two times.

    Query text comes back as Performance Insights stores it, which is cut off at
    about 500 characters and can include literal values from the query, despite
    the `tokenized` name. Treat it as sensitive.

    Raises:
        InvalidWindow: if the window is too long or outside the retained history.
        PerformanceInsightsUnavailable: if AWS can't be reached or refuses.
    """
    period = _period_for(start, end)
    points = _load_points(start, end, period)
    sampled = [p["load"] for p in points if p["load"] is not None]
    average = sum(sampled) / len(sampled) if sampled else 0.0

    users = _top("db.user", ALL_USERS, start, end, period)
    total_load = sum(user["load"] for user in users)

    # Out of the users' total rather than `average`: Performance Insights averages
    # these lists over a slightly different window than the graph's samples, so
    # dividing one by the other gives shares that don't add up.
    def share(load: float) -> float:
        return load / total_load if total_load else 0.0

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "period_seconds": period,
        "vcpus": settings.DATABASE_VCPUS,
        "peak_load": max(sampled, default=0.0),
        "average_load": average,
        "load": points,
        "queries": [
            {
                "id": top["dimensions"].get("db.sql_tokenized.id", ""),
                "statement": top["dimensions"].get("db.sql_tokenized.statement", ""),
                "load": top["load"],
                "share": share(top["load"]),
            }
            for top in _top("db.sql_tokenized", TOP_QUERIES, start, end, period)
        ],
        "users": [
            {
                "name": top["dimensions"].get("db.user.name", ""),
                "load": top["load"],
                "share": share(top["load"]),
            }
            for top in users[:TOP_USERS]
        ],
        "waits": [
            {
                "name": top["dimensions"].get("db.wait_event.name", ""),
                "load": top["load"],
                "share": share(top["load"]),
            }
            for top in _top("db.wait_event", TOP_WAITS, start, end, period)
        ],
    }
