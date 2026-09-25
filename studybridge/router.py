"""A tiny router: maps (HTTP method, path pattern) -> handler function.

Path patterns can contain named parameters, e.g. "/api/bookings/{id}".
When a request comes in for a path that matches no pattern at all, that's
a 404. When the path matches a pattern but not with this method, that's a
405 (the resource exists, you're just using the wrong verb).
"""

import re


class RouteNotFound(Exception):
    """No registered pattern matches this path at all."""


class MethodNotAllowed(Exception):
    """The path matches a pattern, but not with this HTTP method."""


class Router:
    def __init__(self):
        # Each entry: (method, compiled_regex, handler)
        self._routes = []

    def add(self, method, path, handler):
        pattern = self._compile(path)
        self._routes.append((method.upper(), pattern, handler))

    @staticmethod
    def _compile(path):
        if path == "/":
            return re.compile(r"^/$")
        segments = path.strip("/").split("/")
        regex_parts = []
        for segment in segments:
            if segment.startswith("{") and segment.endswith("}"):
                name = segment[1:-1]
                regex_parts.append(f"(?P<{name}>[^/]+)")
            else:
                regex_parts.append(re.escape(segment))
        return re.compile("^/" + "/".join(regex_parts) + "$")

    def resolve(self, method, path):
        """Return (handler, params) for the first pattern that matches path.

        Raises RouteNotFound if no pattern matches the path, or
        MethodNotAllowed if a pattern matches but not with this method.
        """
        path_matched = False
        for route_method, pattern, handler in self._routes:
            match = pattern.match(path)
            if match is None:
                continue
            path_matched = True
            if route_method == method.upper():
                return handler, match.groupdict()
        if path_matched:
            raise MethodNotAllowed()
        raise RouteNotFound()


# One shared router instance. API modules (added from Step 2 onward)
# will import this and call router.add(...) to register their routes.
router = Router()
