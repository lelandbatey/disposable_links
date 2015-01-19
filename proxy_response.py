from __future__ import print_function
from threading import Thread
from Queue import Queue
import posixpath
import urlparse
import urllib2

# from pprint import pprint



class ProxyResponse(object):
    """A WSGI app that proxys a response from a remote host to the client."""
    def __init__(self, url, headers):
        self.url = url
        self.request_headers = headers
        self._response_headers = None
        self._response_code = None
        self.data_queue = Queue()
        self.finished_download = False

        self.open_error = False

        self.download_thread = Thread(target=self.download_file)
        self.download_thread.daemon = True
        self.download_thread.start()

    def download_file(self):
        """Downloads the file in a seperate thread."""
        del self.request_headers['HOST']
        request = urllib2.Request(self.url, headers=self.request_headers)
        try:
            # print("thread: Downloading file", self.url)
            opener = urllib2.urlopen(request, timeout=3)
            # print('thread: Headers:', self.request_headers)
        except urllib2.HTTPError, e:
            self._response_headers = {}
            self._response_code = e.getcode()
            self.finished_download = True
            self.open_error = True
            return
        except Exception, e:
            # print(e.message)
            raise e

        size = int(opener.headers['content-length'])
        chunk_size = size // 20
        chunk_size = 1024 if chunk_size < 1024 else chunk_size

        # print("thread: Setting response headers.")
        self._response_headers = dict(opener.info())
        self._response_code = opener.getcode()

        # print("thread: Begin reading in data.")
        while True:
            chunk = opener.read(chunk_size)
            if not chunk:
                break
            self.data_queue.put(chunk)
        self.finished_download = True

    @property
    def response_code(self):
        """Blocks till the response code is set."""
        while True:
            if self._response_code:
                return self._response_code

    @property
    def response_headers(self):
        """Blocks till the response headers are set."""
        while True:
            if self._response_headers:
                return self._response_headers

    @property
    def filename(self):
        """Figures out the name of file to be downloaded."""
        path = urlparse.urlsplit(self.url).path
        return posixpath.basename(path)

    def __iter__(self):
        """Yeilds the data being downloaded."""
        if self.open_error:
            yield ""
            return
        while not self.finished_download or not self.data_queue.empty():
            if not self.data_queue.empty():
                data = self.data_queue.get()
                yield data


def main():
    """Tests our class."""
    rand_url = "http://f.xwl.me/Adventure.Time.S06E11.Little.Brother.HDTV.x264-W4F.mp4"
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



if __name__ == '__main__':
    main()

