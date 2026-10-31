import math
import threading
import time
from collections import OrderedDict, deque

from app.libs.errors import ApiError

LIMITS = {"demo": (30, 60), "login": (10, 60), "signup": (3, 3600), "reset": (3, 3600)}


class AccountLimiter:
    def __init__(self):
        self.buckets = OrderedDict()
        self.lock = threading.Lock()

    def check(self, scope, peer):
        count, seconds = LIMITS[scope]
        current = time.monotonic()
        key = (scope, peer)
        with self.lock:
            bucket = self.buckets.pop(key, deque())
            while bucket and bucket[0] <= current - seconds:
                bucket.popleft()
            self.buckets[key] = bucket
            while len(self.buckets) > 10000:
                self.buckets.popitem(last=False)
            if len(bucket) >= count:
                raise ApiError(429, retry_after=max(1, math.ceil(bucket[0] + seconds - current)))
            bucket.append(current)
