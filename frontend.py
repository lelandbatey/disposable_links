#!/usr/bin/env python


from __future__ import print_function

# from functools import reduce

import mimetypes
import os.path
import json
import os
import re

from flask import Flask, request, render_template, send_file, Response
from flask.ext.basicauth import BasicAuth
from six.moves import reduce
import six

import database


APP = Flask(__name__)
APP.USE_X_SENDFILE = True


CONFIG = database.ConfigReader()
DBCLASS = database.AlchemyDatabase

APP.config['BASIC_AUTH_USERNAME'] = CONFIG.username
APP.config['BASIC_AUTH_PASSWORD'] = CONFIG.password

basic_auth = BasicAuth(APP)




def get_directory_structure(rootdir):
    """Creates a nested dictionary that represents the folder structure of
    rootdir."""
    directory = {}
    rootdir = rootdir.rstrip(os.sep)
    start = rootdir.rfind(os.sep) + 1
    for path, _, files in os.walk(rootdir):
        folders = path[start:].split(os.sep)
        subdir = {f : os.path.join(path, f) for f in files}
        parent = reduce(dict.get, folders[:-1], directory)
        parent[folders[-1]] = subdir
    return directory

def build_file_tree_html(tree):
    """Transforms a dictionary representing a file tree into a depth-first
    list."""
    def build_level(curr_dir, depth=0):
        """Recursive depth-first file list builder. Given a dictionary
        representing a tree of files/folders, transforms that into a list of
        lists, each sub-list containing two entries:
            0. The name of the node
            1. If the node is a file, the full path to that file. If the node
               is a directory, the value `None`
        Examples:

            input:
                {
                    "thing0": {
                        "second_example": {
                            "ex2.txt": "./files/buckets/thing0/second_example/ex2.txt",
                            "ex2_01.txt": "./files/buckets/thing0/second_example/ex2_01.txt"
                        },
                        "another_thing.txt": "./files/buckets/thing0/another_thing.txt"
                    }
                }

            output:
                [['  thing0', None],
                 ['    another_thing.txt', './files/buckets/thing0/another_thing.txt'],
                 ['    second_example', None],
                 ['      ex2.txt', './files/buckets/thing0/second_example/ex2.txt'],
                 ['      ex2_01.txt', './files/buckets/thing0/second_example/ex2_01.txt']]
        """
        line_list = []
        node_str = ""
        for item in sorted(curr_dir.keys()):
            node_str += "  "*depth
            node_str = ((node_str+item)[:48]+'..') if (len(node_str+item)) > 50 else node_str+item
            if isinstance(curr_dir[item], six.string_types):
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
    for branch in tree:
        lines += build_level(branch)
    return lines


# These next two functions are from here:
#     http://blog.asgaard.co.uk/2012/08/03/http-206-partial-content-for-flask-python
@APP.after_request
def add_range_headers(response):
    """Lets browsers know they can request ranges."""
    response.headers.add('Accept-Ranges', 'bytes')
    return response

def send_file_partial(path, req):
    """
        Simple wrapper around send_file which handles HTTP 206 Partial Content
        (byte ranges)
        TODO: handle all send_file args, mirror send_file's error handling
        (if it has any)
    """
    range_header = req.headers.get('Range', None)
    if not range_header:
        return send_file(path)

    size = os.path.getsize(path)
    byte1, byte2 = 0, None

    range_str = re.search(r'(\d+)-(\d*)', range_header).groups()

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


@APP.route('/')
def root():
    """Serves a blank root."""
    return ""


@APP.route('/add_file/', methods=['GET', 'POST'])
@basic_auth.required
def add_url():
    """Adds a file entry to the database."""
    sql_db = DBCLASS()
    if request.method == 'POST':
        print("Request:", request.get_json(force=True))
        data = request.get_json(force=True)
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


@APP.route('/list_files/')
@basic_auth.required
def get_file_list():
    """Rnders list of files."""
    buckets = []
    for b in CONFIG.buckets:
        tree = get_directory_structure(b)
        print(tree)
        tree = {b: tree[list(tree)[0]]}
        buckets.append(tree)
    print(buckets)
    buckets = build_file_tree_html(buckets)
    print(buckets)

    return render_template('file_list.html', file_struct=buckets, name="File List")


@APP.route('/list_active/')
@basic_auth.required
def list_active():
    """Lists all the possible url's and what they point to."""
    sql_db = DBCLASS()
    return render_template('active_links.html', files=sql_db.to_dict(), name="Active Links")



@APP.route('/get/<file_id>')
def download(file_id):
    """Dummy route to allow flask to properly generate links. This is
    unreachable, since it's manually overriden in the app.py file."""
    return ["Don't know how you got here..."]


@APP.route('/remove/<file_id>')
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

APP.debug = True

if __name__ == '__main__':
    APP.debug = True
    APP.run(host='0.0.0.0', port=5000)
