#!/usr/bin/env python
from __future__ import print_function
from flask import Flask, request, render_template, send_file, Response
from flask.ext.basicauth import BasicAuth
import http_streamer
import mimetypes
import database
import os.path
import json
import os
import re


app = Flask(__name__)
app.USE_X_SENDFILE = True


CONFIG = database.ConfigReader()
DBCLASS = database.AlchemyDatabase

app.config['BASIC_AUTH_USERNAME'] = CONFIG.username
app.config['BASIC_AUTH_PASSWORD'] = CONFIG.password

basic_auth = BasicAuth(app)


def get_file_params(file_id):
    """Gets information about a file, as well as sanity checks."""
    sql_db = DBCLASS()
    tmp = sql_db.get_entry(file_id)

    # Check that the file exists and is valid.
    if not tmp or tmp['is_expired']:
        raise KeyError("Invalid file id.")

    file_location = tmp['file_location']
    is_remote = tmp['is_remote']

    if not tmp['file_exists'] and not is_remote:
        raise KeyError("The file for this id does not exist.")
    return file_location, is_remote


def get_directory_structure(rootdir):
    """
    Creates a nested dictionary that represents the folder structure of rootdir
    """
    dir = {}
    rootdir = rootdir.rstrip(os.sep)
    start = rootdir.rfind(os.sep) + 1
    for path, dirs, files in os.walk(rootdir):
        folders = path[start:].split(os.sep)
        subdir = {f : os.path.join(path, f) for f in files}
        parent = reduce(dict.get, folders[:-1], dir)
        parent[folders[-1]] = subdir
        # print(subdir)
        # print(path)
    return dir

def build_file_tree_html(tree):
    def build_level(curr_dir, depth=0):
        """Makes the lists of transformed file names"""
        line_list = []
        node_str = ""
        for item in sorted(curr_dir.keys()):
            node_str += "  "*depth
            node_str = ((node_str+item)[:48]+'..') if (len(node_str+item)) > 50 else node_str+item
            if isinstance(curr_dir[item], basestring):
                line_list.append([
                    node_str, curr_dir[item]
                ])
            elif isinstance(curr_dir[item], dict):
                line_list.append([
                    node_str, None
                ])
                line_list += build_level(curr_dir[item], depth+1)
            node_str = ""
        return line_list

    lines = []
    for x in tree:
        lines += build_level(x)
    return lines


# These next two functions are from here:
#     http://blog.asgaard.co.uk/2012/08/03/http-206-partial-content-for-flask-python
@app.after_request
def add_range_headers(response):
    """Lets browsers know they can request ranges."""
    response.headers.add('Accept-Ranges', 'bytes')
    return response

def send_file_partial(path, request):
    """
        Simple wrapper around send_file which handles HTTP 206 Partial Content
        (byte ranges)
        TODO: handle all send_file args, mirror send_file's error handling
        (if it has any)
    """
    range_header = request.headers.get('Range', None)
    if not range_header:
        return send_file(path)

    size = os.path.getsize(path)    
    byte1, byte2 = 0, None

    range_str = re.search('(\d+)-(\d*)', range_header).groups()

    if range_str[0]:
        byte1 = int(range_str[0])
    if range_str[1]:
        byte2 = int(range_str[1])

    length = size - byte1
    if byte2 is not None:
        length = byte2 - byte1 + 1

    data = None
    with open(path, 'rb') as t_file:
        t_file.seek(byte1)
        data = t_file.read(length)

    to_return = Response(data, 
                         206,
                         mimetype=mimetypes.guess_type(path)[0], 
                         direct_passthrough=True)
    to_return.headers.add(
        'Content-Range',
        'bytes {0}-{1}/{2}'.format(byte1, byte1 + length - 1, size)
    )

    return to_return


@app.route('/')
def root():
    """Serves a blank root."""
    return ""


@app.route('/add_file/', methods=['GET', 'POST'])
@basic_auth.required
def add_url():
    """Adds a file entry to the database."""
    sql_db = DBCLASS()
    if request.method == 'POST':
        data = json.loads(request.data)
        if 'file_location' in data:
            file_location = data['file_location']
        else:
            raise KeyError("'file_location' not specified in post-data.")
        if 'expiration_delta' in data:
            expiration_delta = int(data['expiration_delta'])
        else:
            expiration_delta = 1
        sql_db.new_entry(file_location, expiration_delta)
        return "success"
    else:
        return render_template('active_links.html', files=sql_db.to_dict(), name="Active Links")


@app.route('/list_files/')
@basic_auth.required
def get_file_list():
    buckets = []
    for b in CONFIG.buckets:
        tree = get_directory_structure(b)
        tree = { b: tree[tree.keys()[0]]}
        buckets.append(tree)
    buckets = build_file_tree_html(buckets)

    return render_template('file_list.html', file_struct=buckets, name="File List")


@app.route('/list_active/')
@basic_auth.required
def list_active():
    """Lists all the possible url's and what they point to."""
    sql_db = DBCLASS()
    return render_template('active_links.html', files=sql_db.to_dict(), name="Active Links")



# This function was originally adapted almost exactly from here:
#     https://gist.github.com/jessejlt/1306827
#
# However, that method doesn't work for crap. The only way that actually
# works, and the best way, is to use the built in `send_file` method.
@app.route('/get/<file_id>')
def download(file_id):
    """Serves the file being requested."""
    file_location, is_remote = get_file_params(file_id)

    def update_file_location(location):
        sql_db = DBCLASS()
        sql_db.update_location(file_id, location)

    if is_remote:
        stream = http_streamer.Streamer(\
            file_location,\
            cache=True,\
            cache_location=CONFIG.cache)
        return Response(stream.generator(update_file_location), mimetype=stream.mimetype)

    else:
        return send_file_partial(file_location, request)


@app.route('/remove/<file_id>')
@basic_auth.required
def remove(file_id):
    sql_db = DBCLASS()

    # To keep disk-space lean, when 
    entry = sql_db.get_entry(file_id)
    tmp = entry['file_location']
    tmp = os.path.join(os.path.abspath(CONFIG.cache), os.path.basename(tmp))

    if os.path.exists(tmp):
        os.remove(tmp)

    sql_db.remove_entry(file_id)
    return ""

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)