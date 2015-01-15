#!/usr/env python
from __future__ import print_function
from flask import Flask, request, json, render_template, send_file
import database
import os.path
import json

app = Flask(__name__)
app.USE_X_SENDFILE = True

DB = database.Database()
DB.new_entry('/tmp/adorableRun.gif')

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



@app.route('/')
def root():
    """Serves a blank root."""
    return ""



@app.route('/add_file/', methods=['GET', 'POST'])
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
        return render_template('file_list.html', files=DB.to_dict())



@app.route('/list_active/')
def list_active():
    """Lists all the possible url's and what they point to."""
    return render_template('file_list.html', files=DB.to_dict())



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