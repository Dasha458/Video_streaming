"""
What this service is doing, in a form Prometheus can scrape.

The endpoint and the scrape job were already here: /api/metrics served a
registry, prometheus.yaml scraped it, and Prometheus reported the target
up. The registry was empty, so the only series under job="ffmpeg" were
the five Prometheus writes about its own scrape. Nothing said how many
videos were encoded, how long they took, or how many failed -- on a
platform whose whole job is encoding video, and after a week of fixing
bugs where encodes failed silently or sat in "processing" for good.
These are the measurements that would have shown both.

The registry is passed in rather than using the default one, so the ASGI
app exposes exactly these and the tests can use a registry of their own.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class EncodeMetrics:
    """Counters and timings for one encoding worker."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.started = Counter(
            "convertor_encodes_started_total",
            "Encode jobs taken off the queue.",
            registry=registry,
        )
        self.finished = Counter(
            "convertor_encodes_finished_total",
            "Encode jobs that reached a terminal state.",
            # "ready" or "failed" -- the same words published back to the
            # backend, so a dashboard and the database agree.
            ["outcome"],
            registry=registry,
        )
        self.in_progress = Gauge(
            "convertor_encodes_in_progress",
            "Encode jobs running right now.",
            registry=registry,
        )
        self.duration = Histogram(
            "convertor_encode_duration_seconds",
            "Wall-clock time from taking a job to publishing its status.",
            # A short clip and a long upload are different problems; the
            # default buckets top out at 10s, which is under a minute of
            # video.
            buckets=(5, 15, 30, 60, 120, 300, 600, 1800, 3600),
            registry=registry,
        )
        self.encoder = Counter(
            "convertor_encoder_used_total",
            "Which encoder actually ran.",
            # "gpu", or "cpu" when NVENC was unavailable or fell over --
            # a silent slide onto CPU is a capacity problem worth seeing.
            ["encoder"],
            registry=registry,
        )
