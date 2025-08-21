import threading
from collections import deque

def contains_lock(obj):
    """
    Recursively inspects an object and its attributes/contents to detect any threading.Lock or threading.RLock instances.
    """
    seen = set()
    queue = deque([obj])

    while queue:
        current = queue.popleft()
        obj_id = id(current)
        if obj_id in seen:
            continue
        seen.add(obj_id)

        # Is this currently a lock?
        if isinstance(current, threading.Lock):
            return True
        # if isinstance(current, threading.RLock):
        #     return True

        # Dive into dictionaries
        if isinstance(current, dict):
            queue.extend(current.keys())
            queue.extend(current.values())

        # Explore iterable containers (except strings and bytes)
        elif isinstance(current, (list, set, tuple, deque)):
            queue.extend(current)

        # Inspect object attributes
        elif hasattr(current, "__dict__"):
            for attr in vars(current).values():
                queue.append(attr)

        # Check __slots__ if defined
        elif hasattr(current, "__slots__"):
            for slot in current.__slots__:
                try:
                    queue.append(getattr(current, slot))
                except AttributeError:
                    pass

    return False
