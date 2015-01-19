#!/usr/bin/env python
from __future__ import print_function
from werkzeug.wsgi import DispatcherMiddleware
from frontend import app as frontend
import proxy_response
import database
import httplib


def extract_request_headers(environ):
    to_return = {}
    for key in environ.keys():
        if key.startswith("HTTP_"):
            to_return[key[5:]] = environ[key]
    return to_return

def get_url(environ):
    """Get's the URL to be fetched."""
    remote = ""
    sql_db = database.SqliteDatabase()
    path_info = environ['PATH_INFO'][1:]

    if "://" not in path_info:
        entry = sql_db.get_entry(path_info)
        if entry:
            remote = entry['file_location']
    else:
        remote = path_info

    return remote

    # return """http://comp.adrenl.in/Pasha%20biceps%20-%20biceps%20is%20always%20with%20you%20-%20sound%20download%20HD-o03JwjEM5yc.mp4"""

def get_status_from_code(code):
    """Returns the proper http response message for a given code."""
    return str(code)+" "+httplib.responses[code]


def simple_app(environ, start_response):
    """
    Proxys a file request back to the client, either via direct streaming or
    from the local cache.
    """

    url = get_url(environ)
    if not url:
        status = get_status_from_code(404)
        start_response(status, [])
        return "404"
    # print(url)

    headers = extract_request_headers(environ)
    fproxy = proxy_response.ProxyResponse(url, headers)

    # print("Getting response headers.")
    response_headers = fproxy.response_headers
    # print("Got response headers.")

    # print("Printing filename:")
    # print(fproxy.filename)
    if response_headers:
        response_headers['Content-Disposition'] =\
            'inline; filename="{}"'.format(fproxy.filename)
    response_headers = [(x, response_headers[x]) for x in response_headers]

    status = get_status_from_code(fproxy.response_code)

    start_response(status, response_headers)
    return fproxy



APPLICATION = DispatcherMiddleware(frontend, {
    '/dl':     simple_app
})



