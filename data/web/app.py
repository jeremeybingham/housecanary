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
from collections import Counter

# imports for Flask-Limiter example
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix


#~ startup
# instantiate logging
logging.basicConfig(format='%(levelname)s|%(asctime)s|%(name)s|%(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO, filename='activity.log', filemode='a+')

# instantiate flask app
app = Flask(__name__)
app.secret_key = os.environ['FLASK_SECRET_KEY']


# instantiate Flask-Limiter for example
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
limiter = Limiter(app, key_func=get_remote_address)


#~ local variables
# mysql connection info
user=os.environ['DB_USER']
password=os.environ['DB_PASSWORD']
host=os.environ['MYSQL_HOST']
db=os.environ['MYSQL_DATABASE']


#~ functions

# create a sqalchemy connection object
def get_cnx(): 
    return create_engine(f'mysql+pymysql://{user}:{password}@{host}:3306/{db}').connect()

# generate the time json package to return
def time_json():

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


# write request info to db for completed requests
def write_row(request_headers):
    
    # create a sqalchemy connection object
    cnx = get_cnx()

    # create a dict for request info 
    info = {}

    # populate with request headers
    info['full_headers'] = str(request_headers)

    # get requester IP from headers
    info['requester'] = str(request_headers.get('X-Forwarded-For', request.remote_addr))

    # create a uid for the request db entry
    info['uid'] = str(uuid.uuid4())

    # sql insert statement to create a new request row
    insert_sql = f"""INSERT INTO {os.environ['MYSQL_TABLE_REQUESTS']} (`uid`,`requester`,`request_time`) VALUES (%s,%s,%s)"""

    # sql parameters for new row - #! is there a server-default time implementation of this SQAlchemy method?
    insert_params = (f'{info["uid"]}', f'{info["requester"]}', datetime.now())

    # execute with the connection
    cnx.execute(insert_sql, insert_params)
    
    # close connection
    cnx.close()


# test all incoming requests for rate limit conditions 
def process_request(request_headers, interval, limit, limit_single_client):

    # get requester ip from headers
    requester_ip = str(request_headers.get('X-Forwarded-For', request.remote_addr))

    # create a sqalchemy connection object
    cnx = get_cnx()

    # fetch requester IP and times of all requests in the last 'interval'*1000 microseconds
    fetch_sql = cnx.execute(f'''SELECT `requester`, `request_time` FROM {os.environ["MYSQL_TABLE_REQUESTS"]} WHERE DATE_ADD(`request_time`, INTERVAL {interval*1000} MICROSECOND) >= NOW(3)''').fetchall()

    # close connection
    cnx.close()

    # convert the fetched rows into a Counter object
    requests_counter = Counter([k for (k,v) in fetch_sql])

    # evaluate how many total requests were returned
    requests_total = sum(requests_counter.values())
    
    # count requests from current client ip in Counter
    current_client_requests = [v for k, v in requests_counter.items() if requester_ip in k]

    # abort with general error if requests_total > limit
    if requests_total > limit:
        abort(429, description=f"429 Too Many Requests - exceeded {limit} in {interval} milliseconds", retry_after={interval/10000})

    # abort with specific client error if current_client_requests > limit_single_client
    elif current_client_requests and current_client_requests[0] > limit_single_client:
        abort(429, description=f"429 Too Many Requests - exceeded {limit_single_client} in {interval} milliseconds from IP: {requester_ip}", retry_after={interval/10000})
    
    else:

        # call our function to create response
        json_response = time_json()

        # log the completed request in the db
        write_row(request_headers)

        # return the response
        return json_response


#~ routes

# serve robots.txt from static directory
@app.route('/robots.txt')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


# root
@app.route('/', methods=['GET'])
def root():
    return 'Hi HouseCanary Team!'


# analyze request headers endpoint - returns all Flask request object header info to screen
@app.route('/headers/', methods=['GET'])
def headers():
    
    return str(request.headers)


# writes a test request row to db, returns request headers to screen
@app.route('/db_test/', methods=['GET'])
def db_test():
    
    # log the test request in the db
    write_row(request.headers)
    
    # print the request headers to screen
    return str(request.headers)


# simple time endpoint, doesn't write to db, not rate-limited, returns time json to screen
@app.route('/time_test/', methods=['GET'])
def time_test():

    # call our function to create response
    json_response = time_json()

    # return the response
    return json_response


# time endpoint
@app.route('/time/', methods=['GET'])
def time():
    
    # set interval and limits
    interval = 60000            # interval to limit requests within, in milliseconds
    limit = 6                   # global request limit in that interval from all clients
    limit_single_client = 3     # limit for a single client in that interval

    return process_request(request.headers, interval, limit, limit_single_client)


# time endpoint 2 - longer limits
@app.route('/time2/', methods=['GET'])
def time2():
    
    # set interval and limits
    interval = 120000            # interval to limit requests within, in milliseconds
    limit = 20                   # global request limit in that interval from all clients
    limit_single_client = 10     # limit for a single client in that interval

    return process_request(request.headers, interval, limit, limit_single_client)


# time endpoint 3 - cheating with Flask-Limiter
@app.route('/time3/', methods=['GET'])
@limiter.limit("3 per minute")
def time3():

    # call our function to create response
    json_response = time_json()

    # return the response
    return json_response
