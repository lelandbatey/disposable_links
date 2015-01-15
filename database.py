from __future__ import print_function
import datetime
import os.path
import random
import json

# These are just some pet debug functions I love to have around. You'll
# probably find them all over the place. It's lazy and I don't care.
class date_handler(json.JSONEncoder):
    """Handles printing of datetime objects in json.dumps."""
    def default(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif hasattr(obj, '__json__'):
            return obj.__json__()
        else:
            return json.JSONEncoder.default(self, obj)

def json_dump(indata):
    """Creates prettified json representation of passed in object."""
    return json.dumps(indata, sort_keys=True, indent=4, \
        separators=(',', ': '), cls=date_handler)
def jp(indata):
    """Prints json representation of object"""
    print(json_dump(indata))

def random_string(s_len=10): # returns nice 6 character strings
    """Returns a random alpha-numeric string of length `s_len` (default 10)"""
    to_return = ""
    i = 0
    while i < s_len:
        if random.randint(0, 1): # If we get a 1, we do letters
            to_return += chr(random.randint(97, 122))
 
        else: # we get a 0, we do a number
            to_return += str(random.randint(1, 9))
        i += 1
    return to_return

def epoch_to_datetime(epoch):
    """Converts an epoch timestamp to datetime."""
    return datetime.datetime.fromtimestamp(epoch)

def datetime_to_epoch(indate):
    """Converts a datetime object to an epoch timestamp."""
    return (indate - datetime.datetime(1970, 1, 1)).total_seconds()


class FileEntry(object):
    """Object representing file entry in the database."""
    def __init__(self, file_id, location, expiration_date):
        self.file_id = file_id
        self.location = location
        self.expiration_date = expiration_date

    @property
    def is_expired(self):
        """Checks if this FileEntry object is past it's expiration date."""
        if self.expiration_date < datetime.datetime.now():
            return True
        return False

    def _build_self_dict(self):
        """Build a dictionary representation of itself."""
        tmp = {}
        tmp['is_expired'] = self.is_expired
        tmp['file_location'] = self.location
        tmp['file_id'] = self.file_id
        tmp['expiration_date'] = str(datetime_to_epoch(self.expiration_date))
        tmp['file_exists'] = os.path.isfile(self.location)
        return tmp

    def __repr__(self):
        return json_dump(self._build_self_dict())
    def __json__(self):
        return self._build_self_dict()
        

class Database(object):
    """Database for holding the file information."""
    def __init__(self):
        self._db = {}
        
    def new_entry(self, location, expiration_delta=1):
        """Creates entry for the new file in the database, returning its id."""
        file_id = random_string()

        now = datetime.datetime.now()
        expiration_date = now + datetime.timedelta(days=expiration_delta)
        
        self._db[file_id] = FileEntry(file_id, location, expiration_date)

        return file_id

    def get_entry(self, file_id):
        """Returns dictionary object for file entry, if it exists."""
        if file_id in self._db:
            return json.loads(str(self._db[file_id]))

        return None

    def remove_entry(self, file_id):
        """Removes the specified file entry."""
        if file_id in self._db:
            del self._db[file_id]

    def to_dict(self):
        """Returns a dict object representing the DB."""
        
        return json.loads(json_dump(self._db))



def main():
    """Testing the classes."""
    d = Database()

    d.new_entry('/tmp/some_file', 1)
    jp(d.to_dict())


if __name__ == '__main__':
    main()


