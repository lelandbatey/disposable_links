# -*- coding: utf-8 -*-

"""Stream a local file."""

import mimetypes
import os.path
import re

from .save_while_stream import get_nocase
from .stream import get_status_from_code


def range_finder(size, range_header):
    """Determine the length, start and stop for a range_header."""
    byte1, byte2 = 0, None
    range_str = re.search('(\d+)-(\d*)', range_header).groups()

    if range_str[0]:
        byte1 = int(range_str[0])
    if range_str[1]:
        byte2 = int(range_str[1])

    length = size - byte1
    if byte2 is not None:
        length = byte2 - byte1 + 1

    return length, byte1, byte2


class StreamLocal(object):
    """Streams the contents of a local file."""
    def __init__(self, path, headers):
        """Init instance variables."""
        self.path = path
        self.headers = headers
        self.response_headers = {
            "Content-Length" : "",
            "Accept-Ranges" : "bytes"
        }
        self.byte_range = None
        self.size = os.path.getsize(location)
        self.response_headers['Content-Length'] = size

        # Calculate our byte range, if that header was passed
        range_header = get_nocase(self.headers, 'range')
        if range_header:
            length, byte1, byte2 = range_finder(size, range_header)

            self.byte_range = [byte1, byte2]
            self.response_headers['Content-Length'] = length
            self.response_headers['Content-Range'] = \
                'bytes {0}-{1}/{2}'.format(byte1, byte1 + length - 1, size)
            self.response_status = get_status_from_code(206)
            self.response_headers['Content-Type'] = mimetypes.guess_type(location)[0]
        else:
            self.response_headers['Content-Length'] = size
            self.response_headers['Content-Type'] = mimetypes.guess_type(location)[0]
            self.response_status = get_status_from_code(200)

    def return_file(self):
        """Generator for the contents of the file."""
        # Calculate start and end byte for file
        size = self.size
        byte1, byte2 = 0, None
        if self.byte_range:
            byte1, byte2 = self.byte_range

        length = size - byte1
        if byte2 is not None:
            length = byte2 - byte1 + 1

        chunk_size = 524288
        data = None
        with open(path, 'rb') as t_file:
            t_file.seek(byte1)
            while True:
                if length < chunk_size:
                    data = t_file.read(length)
                    yield data
                    break
                else:
                    length = length - chunk_size
                    data = t_file.read(chunk_size)
                    yield data










