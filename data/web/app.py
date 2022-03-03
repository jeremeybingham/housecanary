# HouseCanary API Rate Limiter

from flask import Flask, render_template, request, send_from_directory, redirect, url_for
from delorean import Delorean
import uuid
import json
import logging
from sqlalchemy import create_engine
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# instantiate logging
logging.basicConfig(format='%(levelname)s|%(asctime)s|%(name)s|%(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO, filename='activity.log', filemode='a+')


# instantiate flask app
app = Flask(__name__)
limiter = Limiter(app, key_func=get_remote_address, default_limits=["200 per day"])
app.secret_key = os.environ['FLASK_SECRET_KEY']


# serve robots.txt from static directory
@app.route('/robots.txt')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


# root
@app.route('/', methods=['GET'])
def root():
    return 'Hi HouseCanary Team!'

# time endpoint
@app.route('/time/', methods=['GET'])
@limiter.limit("10 per hour")
def time():

    # create a blank dict to hold JSON elements
    time_dict = {}

    # get a tz-adjusted datetime object of the current time
    datetime_now = Delorean().shift('US/Eastern').datetime

    # get an ISO 8601 timestamp
    iso_time_stamp = datetime_now.isoformat()

    # convert it to a friendly string
    time_string = datetime_now.strftime('%A %B %d %Y, %I:%M:%S %p %Z')

    # create a unique id for the request
    uid = str(uuid.uuid4())

    # add elements to dict
    time_dict['iso_time_stamp']=iso_time_stamp
    time_dict['time_string']=time_string
    time_dict['uid']=uid

    # create JSON response
    json_response = json.dumps(time_dict)
    return json_response


# analyze requests endpoint
@app.route('/req/', methods=['GET'])
def req():
    return str(request.headers)
