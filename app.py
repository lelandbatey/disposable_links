#!/usr/env python
from __future__ import print_function
from flask import Flask, request, json, render_template, send_file
from flask.ext.basicauth import BasicAuth
import database
import os.path
import json
import os

app = Flask(__name__)
app.USE_X_SENDFILE = True

DB = database.Database()

app.config['BASIC_AUTH_USERNAME'] = DB.config.username
app.config['BASIC_AUTH_PASSWORD'] = DB.config.password

basic_auth = BasicAuth(app)


def get_file_params(file_id):
    """Gets information about a file, as well as sanity checks."""
    tmp = DB.get_entry(file_id)

    # Check that the file exists and is valid.
    if not tmp or tmp['is_expired']:
        if tmp['is_expired']:
            DB.remove_entry(file_id)
        raise KeyError("Invalid file id.")

    server_path = tmp['file_location']

    if not tmp['file_exists']:
        raise KeyError("The file for this id does not exist.")
    return server_path


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
        for x in curr_dir:
            node_str += "   "*depth
            node_str += (x[:33]+'..') if len(x)+3*depth > 35 else x
            if isinstance(curr_dir[x], basestring):
                line_list.append([
                    node_str, curr_dir[x]
                ])
            elif isinstance(curr_dir[x], dict):
                line_list.append([
                    node_str, None
                ])
                line_list += build_level(curr_dir[x], depth+1)
            node_str = ""
        return line_list

    lines = []
    for x in tree:
        lines += build_level(x)
    return lines



@app.route('/')
def root():
    """Serves a blank root."""
    return ""

@app.route('/list_files/', methods=['GET', 'POST'])
@basic_auth.required
def get_file_list():
    if request.method == 'GET':

        buckets = []
        for b in DB.config.buckets:
            tree = get_directory_structure(b)
            tree = { b: tree[tree.keys()[0]]}
            buckets.append(tree)

        buckets = build_file_tree_html(buckets)

        # buckets = database.json_dump(buckets)
        return render_template('file_list.html', file_struct=buckets)


@app.route('/add_file/', methods=['GET', 'POST'])
@basic_auth.required
def add_url():
    """Adds a file entry to the database."""
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
        DB.new_entry(file_location, expiration_delta)
        return "success"
    else:
        return render_template('active_links.html', files=DB.to_dict())


@app.route('/list_active/')
@basic_auth.required
def list_active():
    """Lists all the possible url's and what they point to."""
    return render_template('active_links.html', files=DB.to_dict())



# This function was originally adapted almost exactly from here:
#     https://gist.github.com/jessejlt/1306827
#
# However, that method doesn't work for crap. The only way that actually
# works, and the best way, is to use the built in `send_file` method.
@app.route('/download/<file_id>')
def download(file_id):
    server_path = get_file_params(file_id)
    return send_file(server_path, as_attachment=True)


if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)