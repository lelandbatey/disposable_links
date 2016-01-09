# -*- coding: utf-8 -*-

"""Allows for streaming of an HTTP url."""

from __future__ import print_function, division

from threading import Thread
from queue import Queue, Full
import urllib.parse as parse
import urllib.request
import urllib.error
import http.client
import os.path
import time

def get_status_from_code(code):
    """Returns the http response message for a given code."""
    return str(code)+" "+http.client.responses[code]


class Stream(object):
    """Stream object will re-stream an http request."""
    def __init__(self, url, headers):
        self.url = url
        self.request_headers = headers
        self._response_headers = None
        self._response_code = None
        self.data_queue = Queue(1)
        self.finished_download = False

        self.open_error = False

        self.download_thread = Thread(target=self.download_file)
        self.download_thread.daemon = True
        self.download_thread.start()

    def download_file(self):
        """Downloads the file in a seperate thread."""
        # Forwarding the "HOST" header would only break things
        if 'HOST' in self.request_headers:
            del self.request_headers['HOST']

        request = urllib.request.Request(self.url, headers=self.request_headers)
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as err:
            self._response_headers = {}
            self._response_code = err.getcode()
            self.finished_download = True
            self.open_error = True
            return
        except Exception as err:
            raise err

        # Chunk size is 0.5 megabytes
        chunk_size = 524288

        headers = response.getheaders()
        self._response_headers = {h: v for h, v in headers }
        self._response_code = response.status

        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            try:
                self.data_queue.put(chunk, block=True, timeout=8)
            except Full:
                break
        self.finished_download = True

    @property
    def response_status(self):
        """Returns response status, blocking till the response code is set."""
        while True:
            if self._response_code:
                return get_status_from_code(int(self._response_code))
            else: time.sleep(0.1)

    @property
    def response_headers(self):
        """Blocks till the response headers are set."""
        while True:
            if self._response_headers:
                return self._response_headers
            else: time.sleep(0.1)

    @property
    def filename(self):
        """Figures out the name of file to be downloaded."""
        path = parse.urlsplit(self.url).path
        return os.path.basename(path)

    def __iter__(self):
        """Yields the data being downloaded."""
        if self.open_error:
            yield ""
            return
        while not self.finished_download or not self.data_queue.empty():
            if not self.data_queue.empty():
                data = self.data_queue.get()
                yield data
            # This sleep is especially important, since it stops the CPU from
            # spending all it's time whirling through this loop and sucking up
            # CPU.
            else: time.sleep(0.1)


