# HouseCanary API Rate Limiter

#~ imports
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, abort
from delorean import Delorean
import uuid
import json
import logging
from sqlalchemy import create_engine
import os
from datetime import datetime

# unused imports
#from flask_limiter import Limiter
#from flask_limiter.util import get_remote_address


#~ startup
# instantiate logging
logging.basicConfig(format='%(levelname)s|%(asctime)s|%(name)s|%(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO, filename='activity.log', filemode='a+')

# instantiate flask app
app = Flask(__name__)
app.secret_key = os.environ['FLASK_SECRET_KEY']

# instantiate Flask-Limiter - commented out in dev, fix settings later as example
#limiter = Limiter(app, key_func=get_remote_address, default_limits=["200 per day"])


#~ local vars
# mysql connection info
user=os.environ['DB_USER']
password=os.environ['DB_PASSWORD']
host=os.environ['MYSQL_HOST']
db=os.environ['MYSQL_DATABASE']


#~ functions
# preprocess requests to be limited
# interval = int representing desired # of milliseconds to look back
# limit = int representing max requests allowed in interval
def process_request_v1(interval, limit):
    
    # convert interval to microseconds
    interval = interval*1000

    # create a sqalchemy connection object
    cnx = create_engine(f'mysql+pymysql://{user}:{password}@{host}:3306/{db}').connect()

    # fetch requester IP and times of all requests in the last {interval} milliseconds
    fetch_sql = cnx.execute(f'''SELECT `requester`, `request_time` FROM {os.environ["MYSQL_TABLE_REQUESTS"]} WHERE DATE_ADD(`request_time`, INTERVAL {interval} MICROSECOND) >= NOW(3)''').fetchall()

    # close connection
    cnx.close()

    # evaluate how many requests were returned and return false if > limit
    if len(fetch_sql) > limit:
        return False

    else:
        return True


#~ routes

# serve robots.txt from static directory
@app.route('/robots.txt')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


# root
@app.route('/', methods=['GET'])
def root():
    return 'Hi HouseCanary Team!'


# simple time endpoint
@app.route('/time/', methods=['GET'])
def time():

    # create a blank dict to hold JSON elements
    time_dict = {}

    # get a tz-adjusted datetime object of the current time in US-Eastern
    datetime_now = Delorean().shift('US/Eastern').datetime

    # get an ISO 8601 timestamp from datetime_now
    iso_time_stamp = datetime_now.isoformat()

    # convert ISO 8601 timestamp to a friendly string
    time_string = datetime_now.strftime('%A %B %d %Y, %I:%M:%S %p %Z')

    # create a unique id for the request
    uid = str(uuid.uuid4())

    # add elements to a dict
    time_dict['iso_time_stamp']=iso_time_stamp
    time_dict['time_string']=time_string
    time_dict['uid']=uid

    # create JSON response from dict
    json_response = json.dumps(time_dict)

    # return the response
    return json_response

# simple time endpoint 2, manual limits, does not write to DB
@app.route('/time2/', methods=['GET'])
def time2():

    interval = 300000 # 5 minutes in mills
    limit = 2

    if process_request_v1(interval, limit) == False:
        abort(429, description="Too Many Requests on time2 Endpoint")

    else: 

        # create a blank dict to hold JSON elements
        time_dict = {}

        # get a tz-adjusted datetime object of the current time in US-Eastern
        datetime_now = Delorean().shift('US/Eastern').datetime

        # get an ISO 8601 timestamp from datetime_now
        iso_time_stamp = datetime_now.isoformat()

        # convert ISO 8601 timestamp to a friendly string
        time_string = datetime_now.strftime('%A %B %d %Y, %I:%M:%S %p %Z')

        # create a unique id for the request
        uid = str(uuid.uuid4())

        # add elements to a dict
        time_dict['iso_time_stamp']=iso_time_stamp
        time_dict['time_string']=time_string
        time_dict['uid']=uid

        # create JSON response from dict
        json_response = json.dumps(time_dict)

        # return the response
        return json_response


# analyze request headers endpoint - prints all Flask request object header info to screen
@app.route('/req/', methods=['GET'])
def req():
    return str(request.headers)


# manually create a db row for testing, prints request info to screen
@app.route('/manual/', methods=['GET'])
def manual():

    # create a sqalchemy connection object
    cnx = create_engine(f'mysql+pymysql://{user}:{password}@{host}:3306/{db}').connect()

    # create a dict for request info 
    info = {}

    info['full_headers'] = str(request.headers)

    # get requester IP from headers
    info['requester'] = str(request.headers.get('X-Forwarded-For', request.remote_addr))

    # create a uid for the request db entry
    info['uid'] = str(uuid.uuid4())

    # sql insert statement to create a new request row
    insert_sql = f"""INSERT INTO {os.environ['MYSQL_TABLE_REQUESTS']} (`uid`,`requester`,`request_time`) VALUES (%s,%s,%s)"""

    # sql parameters for new row - #! see if there is a "server-default" time implementation of this SQAlchemy method?
    insert_params = (f'{info["uid"]}', f'{info["requester"]}', datetime.now())

    # execute with the connection
    cnx.execute(insert_sql, insert_params)
    
    # close connection
    cnx.close()

    # return the info dict
    return info


# preflight test endpoint - cerify output of interval evals with hardcoded vars
@app.route('/preflight/', methods=['GET'])
def preflight():
    
    # create a sqalchemy connection object
    cnx = create_engine(f'mysql+pymysql://{user}:{password}@{host}:3306/{db}').connect()

    # fetch requester IP and times of all requests in the last 300000000 microseconds (300000 milliseconds)
    fetch_sql = cnx.execute(f'''SELECT `requester`, `request_time` FROM {os.environ["MYSQL_TABLE_REQUESTS"]} WHERE DATE_ADD(`request_time`, INTERVAL 300000000 MICROSECOND) >= NOW(3)''').fetchall()

    # close connection
    cnx.close()

    # evaluate how many requests were returned and abort if > 2
    # flask abort method handles this here but if  should trigger 429 error, generally
    if len(fetch_sql) > 2:
        abort(429, description="Too Many Requests!")

    else:

        # pack into payload
        returned_package = {}
        returned_package['pkg'] = fetch_sql
        returned_package['count'] = len(fetch_sql)

        # return the info dict
        return str(returned_package)
