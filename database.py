from __future__ import print_function
from sqlalchemy import create_engine
import datetime
import sqlite3
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

class ConfigReader(object):
    """Reads the configuration from a file."""
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.username = ""
        self.password = ""
        self.buckets = ""
        self.cache = ""
        self.view_directories = ""
        self.read_config()

    def read_config(self):
        """Reads variables from config file into class."""
        c = json.load(open(self.config_file, 'r'))
        def panic(err):
            print(err)
            exit()

        if not 'username' in c:
            panic("Config file must specify username.")
        if not 'password' in c:
            panic("Config file must specify password.")
        if not 'buckets' in c:
            panic("Config file must specify at least one bucket (viewable directory).")
        if not 'cache' in c:
            panic("Config file must specify a cache directory.")

        self.username = c['username']
        self.password = c['password']
        self.buckets = c['buckets']
        self.cache = c['cache']

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker

BASE = declarative_base()

class FileEntry(BASE):
    """Class to hold entry for a file."""
    __tablename__ = "files"
    file_id = Column(String, primary_key=True)
    expiration_date = Column(String)
    local_location = Column(String)
    remote_location = Column(String)
    download_count = Column(Integer)
    lock = Column(Integer, default=0)

    def __init__(self, file_id, expiration_date, local_location="", \
        remote_location="", download_count=0):
        self.file_id = file_id
        self.expiration_date = expiration_date
        self.local_location = local_location
        self.remote_location = remote_location
        self.download_count = download_count

    def is_expired(self):
        """
        Returns true if the current time is past the expiration date of the
        FileEntry object.
        """
        expire_date = epoch_to_datetime(float(self.expiration_date))
        if expire_date < datetime.datetime.now():
            return True
        return False

    @property
    def file_location(self):
        """Helper for getting the 'file_location' property."""
        if self.local_location:
            return self.local_location
        if self.remote_location:
            return self.remote_location
        return None

    @property
    def is_remote(self):
        if not self.local_location:
            if self.remote_location:
                return True
        return False

    @property
    def file_exists(self):
        if self.local_location:
            if os.path.isfile(self.local_location):
                return True
            else:
                return False
        if self.is_remote:
            return True
        return False

    def to_json(self):
        """Return a json object of this instance."""
        return {
            'file_id' : self.file_id,
            'file_location': self.file_location,
            'file_exists' : self.file_exists,
            'expiration_date' : self.expiration_date,
            'local_location' : self.local_location,
            'remote_location' : self.remote_location,
            'download_count' : self.download_count,
            'is_expired' : self.is_expired(),
            'is_remote' : self.is_remote,
            'is_locked' : self.lock
        }

    def __repr__(self):
        return json_dump(self.to_json())



class AlchemyDatabase(object):
    """Database for holding file info. Uses SQLAlchemy as backend."""
    def __init__(self, db_name="links_database.sqlite3"):
        self.db_name = db_name
        self.db = create_engine("sqlite:///"+db_name)
        self.session_class = sessionmaker()
        self.session_class.configure(bind=self.db)
        self.session = self.session_class()
        FileEntry.metadata.create_all(self.db, checkfirst=True)

    def new_entry(self, local_location, expire_delta=1, remote_location=""):
        """Create a new file entry object and store it in the database."""

        file_id = random_string()
        now = datetime.datetime.now()
        expiration_date = now + datetime.timedelta(days=expire_delta)
        expire_date = datetime_to_epoch(expiration_date)

        # Be very strict about what is the local vs remote location
        if "://" in local_location:
            remote_location = local_location
            local_location = ""

        entry = FileEntry(file_id, remote_location=remote_location,\
            local_location=local_location, expiration_date=str(expire_date))
        self.session.add(entry)
        self.session.commit()

    def remove_entry(self, file_id):
        """Deletes the FileEntry with the given file_id from the database."""
        entry = self.session.query(FileEntry).filter_by(file_id=file_id).first()
        if entry:
            self.session.delete(entry)
            self.session.commit()

    def get_entry(self, file_id):
        """Returns dict representing given FileEntry."""
        entry = self.session.query(FileEntry).filter_by(file_id=file_id).first()
        if entry:
            return entry.to_json()

    def to_dict(self):
        """Returns dict representing all rows in Database."""
        to_return = {}
        entries = self.session.query(FileEntry).all()
        for entry in entries:
            to_return[entry.file_id] = entry.to_json()
        return to_return

    def update_location(self, file_id, local_location):
        """Changes the local location for the given FileEntry."""
        entry = self.session.query(FileEntry).filter_by(file_id=file_id).first()
        if entry:
            entry.local_location = local_location
            self.session.commit()

    def is_locked(self, file_id):
        """Returns true if the given file_id has a lock of '1'."""
        entry = self.session.query(FileEntry).filter_by(file_id=file_id).first()
        if not entry:
            raise KeyError("No entry with that file_id exists.")
        if entry.lock == 0:
            return False
        elif entry.lock == 1:
            return True

    def lock_entry(self, file_id):
        """Locks an entry with given file_id."""
        print("Locking entry:", file_id)
        entry = self.session.query(FileEntry).filter_by(file_id=file_id).first()
        if not entry:
            raise KeyError("No entry with that file_id exists.")
        if entry.lock == 0:
            entry.lock = 1
            self.session.commit()
        elif entry.lock == 1:
            raise RuntimeError("Entry with given file_id is already locked.")

    def unlock_entry(self, file_id):
        """Unlocks an entry with the given file_id."""
        entry = self.session.query(FileEntry).filter_by(file_id=file_id).first()
        if not entry:
            raise KeyError("No entry with that file_id exists.")
        entry.lock = 0
        self.session.commit()

    def is_cached(self, file_id):
        """Returns true if the entry has a local location."""
        entry = self.session.query(FileEntry).filter_by(file_id=file_id).first()
        if not entry:
            raise KeyError("No entry with that file_id exists.")
        if entry.local_location:
            return True
        return False






def main():
    """Testing the classes."""
    # d = Database()
    d = AlchemyDatabase()

    test_file = "/tmp/some_file"

    d.new_entry(test_file, 1)
    dump = d.to_dict()
    # for x in dump:
    #     if dump[x]['local_location'] == test_file:
    #         d.remove_entry(x)
    jp(d.to_dict())


if __name__ == '__main__':
    main()


