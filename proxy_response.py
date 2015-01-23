from __future__ import print_function
from threading import Thread
from Queue import Queue, Full
import mimetypes
import urlparse
import os.path
import urllib2
import httplib
import time
import re

def get_nocase(d, v):
    for key in d.keys():
        if key.lower() == v.lower():
            return d[key]
    return None

def get_status_from_code(code):
    """Returns the proper http response message for a given code."""
    return str(code)+" "+httplib.responses[code]


class OtherResponse(object):
    """WSGI response to for a non-valid request."""
    def __init__(self):
        self.response_status = get_status_from_code(404)
        self.response_headers = {}

    def __iter__(self):
        return iter(["404"])
        

class CacheResponse(object):
    """
    WSGI middleware to serve a cached response if available, or to create a
    passthrough response while simultaneously caching the file if it hasn't
    been cached yet.
    """
    def __init__(self, file_id, request_headers, database, config):
        self.file_id = file_id
        self.request_headers = request_headers
        self.database = database
        self.config = config
        self.response_headers = {
            "Content-Length" : "",
            "Accept-Ranges" : "bytes"
        }
        self.response_status = None
        self.download_thread = None

        self.is_cached = self.database.is_cached(file_id)
        self.passthrough = None
        self.byte_range = []

        if not self.is_cached:
            print("File is not cached.")
            entry = self.database.get_entry(file_id)
            self.passthrough = ProxyResponse(entry['remote_location'], request_headers)
            self.response_headers = self.passthrough.response_headers
            self.response_status = self.passthrough.response_status

            self.download_thread = Thread(target=self.download_to_disk)
            self.download_thread.daemon = True
            self.download_thread.start()

        elif self.is_cached:
            entry = self.database.get_entry(self.file_id)
            location = entry['local_location']
            size = os.path.getsize(location)
            range_header = get_nocase(self.request_headers, 'range')
            if range_header:
                byte1, byte2 = 0, None
                range_str = re.search('(\d+)-(\d*)', range_header).groups()

                if range_str[0]:
                    byte1 = int(range_str[0])
                if range_str[1]:
                    byte2 = int(range_str[1])

                length = size - byte1
                if byte2 is not None:
                    length = byte2 - byte1 + 1

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

    @property
    def filename(self):
        """Get's the filename for the requested object."""
        entry = self.database.get_entry(self.file_id)
        return os.path.basename(entry['local_location'])


    def download_to_disk(self):
        """Downloads a file to the cache directory."""
        import database
        db = database.AlchemyDatabase()
        # If this is locked, then don't download the file.
        if db.is_locked(self.file_id):
            return
        db.lock_entry(self.file_id)
        print("Downloading file to disk.")
        try:
            if 'HOST' in self.request_headers: 
                del self.request_headers['HOST']
            
            url = db.get_entry(self.file_id)['remote_location']
            request = urllib2.Request(url, headers=self.request_headers)
            try:
                opener = urllib2.urlopen(request, timeout=3)
            except Exception as err:
                raise err

            fname = os.path.basename(urlparse.urlsplit(url).path)
            cache_location = os.path.abspath(self.config.cache)
            location = os.path.join(cache_location, fname)
            cache_file = open(location, 'wb')

            # Chunk size is 0.5 megabytes
            chunk_size = 524288

            while True:
                chunk = opener.read(chunk_size)
                if not chunk:
                    break
                cache_file.write(chunk)
            # File has been downloaded
            db.update_location(self.file_id, location)
            db.unlock_entry(self.file_id)            
        except Exception as err:
            print("Encountered err while downloading to disk: ", err)
            raise err
        finally:
            db.unlock_entry(self.file_id)
            print("Database has been unlocked.")

    def return_file(self, byte1=0, byte2=None):
        """Reads a file, or part of a file, and yields it as an iterable."""
        location = self.database.get_entry(self.file_id)['local_location']

        size = os.path.getsize(location)
        length = size - byte1
        if byte2 is not None:
            length = byte2 - byte1 + 1

        chunk_size = 524288
        data = None
        with open(location, 'rb') as t_file:
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

    def __iter__(self):
        """Handles each request case.

        The different cases are:
        1. Uncached request
        2. Cached request (no range headers)
        3. Cached request *with* range headers
        """


        yieldable = None
        if not self.is_cached:
            yieldable = self.passthrough
        elif self.is_cached:
            if self.byte_range:
                yieldable = self.return_file(
                    self.byte_range[0], self.byte_range[1])
            else:
                yieldable = self.return_file()

        for thing in yieldable:
            yield thing




class ProxyResponse(object):
    """A WSGI app that proxys a response from a remote host to the client."""
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
        if 'HOST' in self.request_headers: del self.request_headers['HOST']
        request = urllib2.Request(self.url, headers=self.request_headers)
        try:
            # print("thread: Downloading file", self.url)
            opener = urllib2.urlopen(request, timeout=3)
            # print('thread: Headers:', self.request_headers)
        except urllib2.HTTPError as err:
            self._response_headers = {}
            self._response_code = err.getcode()
            self.finished_download = True
            self.open_error = True
            return
        except Exception as err:
            # print(e.message)
            raise err

        # size = int(opener.headers['content-length'])
        # Chunk size is 0.5 megabytes
        chunk_size = 524288

        self._response_headers = dict(opener.info())
        self._response_code = opener.getcode()

        # if self.should_cache:
        #     fname = self.filename
        #     location = os.path.join(os.path.abspath(self.cache_location), fname)
        #     c_file = open(location, 'wb')

        # print("thread: Begin reading in data.")
        # import datetime
        while True:
            chunk = opener.read(chunk_size)
            if not chunk:
                break
            # If the client hasn't read 0.5 mb of data in 5 seconds, assume
            # that the client has disconnected and exit this thread. The
            # timeout for this must accomadate for slow clients, since a
            # sufficiently slow client will not empty the queue in time.
            try:
                # start = (datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds()
                self.data_queue.put(chunk, block=True, timeout=8)
                # end = (datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds()
                # print("Time in queue:", end-start)
                # if self.should_cache:
                #     c_file.write(chunk)
            except Full:
                # print("Client has disconnected, stopping reading.")
                break
        self.finished_download = True
        # if self.update_callback:
        #     self.update_callback(location)
        # print("Finished download!")

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
        path = urlparse.urlsplit(self.url).path
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


def main():
    """Tests our class."""
    rand_url = "http://comp.adrenl.in/Adventure.Time.S06E11.Little.Brother.HDTV.x264-W4F.mp4"
    headers = {
        'ACCEPT': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'ACCEPT_ENCODING': 'gzip, deflate',
        'ACCEPT_LANGUAGE': 'en-US,en;q=0.5',
        'CACHE_CONTROL': 'max-age=0',
        'CONNECTION': 'keep-alive',
        'COOKIE': '_ga=GA1.1.1476911807.1406177077; SESSION-GUID=7hrkjh3w98m',
        # 'HOST': 'localhost:9999',
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 6.3; WOW64; rv:35.0) Gecko/20100101 Firefox/35.0'
    }
    file_response = ProxyResponse(rand_url, headers)
    print(file_response.response_headers)
    print(file_response.filename)

    for _ in file_response:
        pass
    print("Finished fetching file response.")


def profile():
    """Checks how fast it takes to download a file."""
    import cProfile
    cProfile.run('main()')



if __name__ == '__main__':
    # main()
    profile()

