#!/usr/bin/env python
from __future__ import print_function
from werkzeug.wsgi import DispatcherMiddleware
from frontend import app as frontend
import proxy_response
import database as appdb
import httplib
import urllib
import gc


# This is a weird way to create a sort of 'enum'
class RequestType:
    class is_neither:
        direct = "direct"
        file_id = "file_id"
        def __eq__(self, other):
            return not (other == self.direct or other == self.file_id)
        def __ne__(self, other):
            return not self.__eq__(other)
    other = is_neither()
    direct = is_neither.direct
    file_id = is_neither.file_id



def extract_request_headers(environ):
    """Extracts the request headers sent by the client from the environment variables."""
    to_return = {}
    for key in environ.keys():
        if key.startswith("HTTP_"):
            to_return[key[5:]] = environ[key]
    return to_return

def format_response_headers(response):
    """Formats a dictionary of response headers into a list of tuples."""
    raw_headers = response.response_headers
    try:
        if not proxy_response.get_nocase(raw_headers, 'Content-Disposition'):
            raw_headers['Content-Disposition'] =\
            'inline; filename="{}"'.format(response.filename)
    except Exception:
        pass
    raw_headers = [(x, raw_headers[x]) for x in raw_headers]
    return raw_headers



def get_url(environ):
    """Get's the URL to be fetched."""
    should_cache = remote = file_id = None
    sql_db = appdb.AlchemyDatabase()
    path_info = environ['PATH_INFO'][1:]

    if "://" not in path_info:
        entry = sql_db.get_entry(path_info)
        if entry:
            remote = entry['file_location']
            file_id = path_info
            should_cache = True
    else:
        should_cache = False
        remote = path_info
        # URL's embeded in the path of the request are unescaped, which makes
        # for invalid requests on the backend. So we have to re-escape them.
        #
        # Since the url was unescaped, if we escape the entire thing we'll
        # accidentally escape the 'scheme' section of the url. So, we skip the
        # first bit (arbitrary amount) of the url when re-encoding.
        remote = "".join([remote[:8], urllib.quote(remote[8:])])
    return remote, should_cache, file_id



def get_request_type(request_value):
    """Returns the type of the request, as well as the remote path to the file."""
    request_type = None
    sql_db = appdb.AlchemyDatabase()
    # path_info = environ['PATH_INFO'][1:]

    if "://" not in request_value:
        entry = sql_db.get_entry(request_value)
        if entry:
            request_type = RequestType.file_id
    else:
        request_type = RequestType.direct
    return request_type


def encode_url(request_value):
    """Properly encodes a url from our environment."""
    # URL's embeded in the path of the request are unescaped, which makes
    # for invalid requests on the backend. So we have to re-escape them.
    #
    # If we escape the entire thing we'll
    # accidentally escape the 'scheme' section of the url. So, we skip the
    # first bit (arbitrary amount) of the url when re-encoding.
    return "".join([request_value[:8], urllib.quote(request_value[8:])])


def get_status_from_code(code):
    """Returns the proper http response message for a given code."""
    return str(code)+" "+httplib.responses[code]


def caching_proxy(environ, start_response):
    """
    Proxys a file request back to the client, either via direct streaming or
    from the local cache.

    Three possible values could be sent for this URL:

    1. Direct url
    2. file_id
    3. A non-valid string

    For each type of request, there is a proper procedure and response:

    1. Direct url
        - Respond directly by re-streaming the file from the remote location
    2. file_id
        - If the file is cached:
            - Respond with cached file
        - If the file is not cached
            - Download the file
            - Cache the response
            - Respond with file
    3. A non-valid string
        - Respond with error
    """
    gc.collect()

    response = status = None

    request_value = environ['PATH_INFO'][1:]
    request_headers = extract_request_headers(environ)
    request_type = get_request_type(request_value)

    if request_type == RequestType.direct:
        url = encode_url(request_value)
        response = proxy_response.ProxyResponse(url, request_headers)
    elif request_type == RequestType.file_id:
        sql_db = appdb.AlchemyDatabase()
        file_id = request_value
        config = appdb.ConfigReader()
        response = proxy_response.CacheResponse(
            file_id,
            request_headers,
            sql_db,
            config
        )
    elif request_type == RequestType.other:
        response = proxy_response.OtherResponse()

    response_headers = format_response_headers(response)
    status = response.response_status
    print(status, response_headers)
    print(response)
    start_response(status, response_headers)
    return response


APPLICATION = DispatcherMiddleware(frontend, {
    '/get': caching_proxy
})

def test_enum():
    vals = ['blag', '://', 'x78x5w653x']
    for v in vals:
        request_type = get_request_type(v)
        print(v)
        if request_type == RequestType.direct: print('direct')
        elif request_type == RequestType.file_id: print('file_id')
        elif request_type == RequestType.other: print('other')
        else: print("Not any type of request (this is bad)")


if __name__ == '__main__':
    # test_enum()
    # Run a debug server
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, APPLICATION, use_reloader=True)


