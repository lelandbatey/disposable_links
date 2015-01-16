from __future__ import print_function
import posixpath
import urlparse
import urllib2
import os.path
import os


class Streamer(object):
    """Enables simultaneous downloading and re-streaming of a file."""
    def __init__(self, remote_url, cache=False, cache_location=""):
        self.remote_url = remote_url
        self.cache = cache
        self.cache_location = cache_location
        self.opener = None
        self._mimetype = None
        self._size = None
        self._filname = None

    def generator(self, callback=None):
        """Yields chunks of the downloaded files."""
        if self.opener == None:
            self.opener = urllib2.urlopen(self.remote_url)

        # If the file's small, download in fixed chunks
        chunk_size = self.size // 20
        chunk_size = 5000 if chunk_size < 5000 else chunk_size

        if self.cache:
            fname = self.filename()
            location = os.path.join(os.path.abspath(self.cache_location), fname)
            c_file = open(location, 'wb')

        while True:
            chunk = self.opener.read(chunk_size)
            if not chunk:
                break
            if self.cache:
                c_file.write(chunk)
            yield chunk

        if callback != None:
            callback(location)

    def filename(self):
        """Determines name of the file."""
        if self._filname == None:
            path = urlparse.urlsplit(self.remote_url).path
            self._filname = posixpath.basename(path)
        return self._filname

    @property
    def size(self):
        """Handles determining size of the file."""
        if self._size == None:
            if self.opener == None:
                self.opener = urllib2.urlopen(self.remote_url)
            self._size = self.opener.headers['content-length']
            self._size = int(self._size)
        return self._size

    @property
    def mimetype(self):
        """Figures out mimetype if unknown."""
        if not self._mimetype:
            if self.opener == None:
                self.opener = urllib2.urlopen(self.remote_url)
            info = self.opener.info()
            self._mimetype = info.type
        return self._mimetype










