# -*- coding: utf-8 -*-

"""Conduct simultaneous streaming and saving of a url."""

from threading import Thread

from .stream import Stream


def get_nocase(d, v):
    """Get's a value from a dictionary case insensitively."""
    for key in d.keys():
        if key.lower() == v.lower():
            return d[key], key
    return None

class SaveStream(object):
    """Saves a stream to a location. Does not re-stream the file."""
    def __init__(self, url, headers, save_path, save_complete_cb=None):
        self.url = url
        self.headers = headers

        # Saving the stream if it's a range stream would result in an
        # incomplete file. Strip the range header if it's passed.
        val = get_nocase(self.headers, 'range')
        if val:
            del self.headers[val[1]]

        self.save_path = save_path
        self.save_complete_cb = save_complete_cb

        self.stream = Stream(self.url, self.headers)
        self.download_thread = Thread(target=self.download_to_file)
        self.download_thread.daemon = True
        self.download_thread.start()

    def __getattr__(self, name):
        """Passthrough to methods of underlying stream method."""
        def passthrough(*args, **kwargs):
            """Implement passthrough."""
            func = getattr(self.stream, name)
            return func(*args, **kwargs)
        return passthrough

    def download_to_file(self):
        """Save the stream to a file."""
        with open(self.save_path, 'wb') as cache_file:
            for data in self.stream:
                cache_file.write(data)
        # Afterward, run the callback
        self.save_complete_cb()


