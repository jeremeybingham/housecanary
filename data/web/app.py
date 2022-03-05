# HouseCanary API Rate Limiter

#~ imports
from flask import Flask, request, send_from_directory, abort
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

# instantiate Flask-Limiter for example 4
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
limiter = Limiter(app, key_func=get_remote_address)


#~ global variables

# mysql connection info
user=os.environ['DB_USER']
password=os.environ['DB_PASSWORD']
host=os.environ['MYSQL_HOST']
db=os.environ['MYSQL_DATABASE']

# global interval and limits for endpoint /time3
global_interval = 60000            # interval to limit requests within, in milliseconds
global_limit = 6                  # global request limit in that interval from all clients
global_limit_single_client = 3     # limit for a single client in that interval

#~ functions

# create a sqalchemy connection object
def get_cnx(): 
    return create_engine(f'mysql+pymysql://{user}:{password}@{host}:3306/{db}').connect()


# generate the time json package to return from endpoints
def time_json():

    # create a blank dict to hold JSON elements
    time_dict = {}

    # get a tz-adjusted datetime object of the current time in US-Eastern
    datetime_now = Delorean().shift('US/Eastern').datetime

    # get an ISO 8601 timestamp from datetime_now
    iso_time_stamp = datetime_now.isoformat()

    # convert ISO 8601 timestamp to a friendly string
    friendly_time = datetime_now.strftime('%A %B %d %Y, %I:%M:%S %p %Z')

    # create a unique id for the request
    uid = str(uuid.uuid4())

    # add elements to a dict
    time_dict['iso_time_stamp']=iso_time_stamp
    time_dict['friendly_time']=friendly_time
    time_dict['uid']=uid

    # create JSON response from dict
    json_response = json.dumps(time_dict)

    # return the response
    return json_response


# write request info to db for completed requests, accepts request.headers from a Flask route request
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
# accepts request.headers, interval and limits from a time endpoint/request
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

    # evaluate how many total requests were returned in Counter
    requests_total = sum(requests_counter.values())
    
    # count requests from current client ip in Counter
    current_client_requests = [v for k, v in requests_counter.items() if requester_ip in k]

    # abort with general error if requests_total >= limit
    if requests_total >= limit:
        return abort(429, description=f"429 Too Many Requests - exceeded {limit} in {interval} milliseconds", retry_after={interval/10000})

    # abort with specific client error if current_client_requests >= limit_single_client
    elif current_client_requests and int(current_client_requests[0]) >= limit_single_client:
        return abort(429, description=f"429 Too Many Requests - exceeded {limit_single_client} in {interval} milliseconds from IP: {requester_ip}", retry_after={interval/10000})
    
    # if everything is OK, just return True
    else:
        return True


# test if rate limit has currently been reached, matching endpoint limit conditions
def test_limit(interval, limit, limit_single_client):

    # create a sqalchemy connection object
    cnx = get_cnx()

    # fetch requester IP and times of requests in the last 'interval' * 1000 microseconds
    fetch_sql = cnx.execute(f'''SELECT `requester`, `request_time` FROM {os.environ["MYSQL_TABLE_REQUESTS"]} WHERE DATE_ADD(`request_time`, INTERVAL {interval*1000} MICROSECOND) >= NOW(3)''').fetchall()

    # close connection
    cnx.close()

    # convert the fetched rows into a Counter object
    requests_counter = Counter([k for (k,v) in fetch_sql])

    # if Counter object exists, evaluate it
    if requests_counter:

        # evaluate how many total requests were returned in Counter
        requests_total = sum(requests_counter.values())
        
        # number of requests from IP with the most requests in the interval
        #! if any requester has exceeded limit, test is true
        top_single_client_requests = Counter([k for (k,v) in fetch_sql]).most_common(1)[0]

        # rate is currently limited if requests_total >= limit
        if requests_total >= limit:
            return True

        # rate is currently limited if top_single_client_requests >= limit_single_client
        elif int(top_single_client_requests[1]) >= limit_single_client:
            return True

        # if no limiter conditions are met in Counter contents, rate is not currently limited, return false
        else: 
            return False
    
    # if no counter/rows returned exist, rate is not currently limited, return False
    else:
        return False


#~ routes

# serve robots.txt from static directory
@app.route('/robots.txt')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


# root
@app.route('/', methods=['GET'])
def root():
    return 'Hi HouseCanary Team! <br> https://github.com/mansard/housecanary'


# time1 endpoint - test 1, requests limited to 6/minute global and 3/minute per IP
@app.route('/time1/', methods=['GET'])
def time1():
    
    # set interval and limits for this endpoint
    interval = 60000            # interval to limit requests within, in milliseconds
    limit = 6                   # global request limit in that interval from all clients
    limit_single_client = 3     # limit for a single client in that interval

    # check if limits have been exceeded
    request_check = process_request(request.headers, interval, limit, limit_single_client)
    
    # request check will abort request automatically if limit exceeded, or return True if OK to serve request
    if request_check == True:

        # call time function to create response
        json_response = time_json()

        # log the completed request in the db
        write_row(request.headers)

        # return the response
        return json_response

# time1 endpoint status check 
@app.route('/time1_status/', methods=['GET']) 
def time1_status():
    
    # set interval and limits for this endpoint, these could be globals if no need for multiple limiting strategies
    interval = 60000            # interval to limit requests within, in milliseconds
    limit = 6                   # global request limit in that interval from all clients
    limit_single_client = 3     # limit for a single client in that interval

    # check status of endpoint by simulating a request with 'test_limit'
    # returns true if limit exceeded, send unavailable response as json
    if test_limit(interval, limit, limit_single_client) == True:
        response = {'status': 'unavailable', 'limit_exceeded': 'True', 'retry-after':f'{interval}', 'http_code': '429 Too Many Requests'}
        return json.dumps(response)
    
    # returns false if limit not exceeded, send available/OK response as json
    else: 
        response = {'status': 'available', 'limit_exceeded': 'False', 'retry-after':'0', 'http_code': '200 OK'}
        return json.dumps(response)


# time2 endpoint - longer limits
@app.route('/time2/', methods=['GET'])
def time2():
    
    # set interval and limits
    interval = 120000            # interval to limit requests within, in milliseconds
    limit = 20                   # global request limit in that interval from all clients
    limit_single_client = 10     # limit for a single client in that interval

    return process_request(request.headers, interval, limit, limit_single_client)

# time2 endpoint status check 
@app.route('/time2_status/', methods=['GET']) 
def time2_status():
    
    # set interval and limits
    interval = 120000            # interval to limit requests within, in milliseconds
    limit = 20                   # global request limit in that interval from all clients
    limit_single_client = 10     # limit for a single client in that interval

    # check status of endpoint by simulating a request with 'test_limit'
    # returns true if limit exceeded, send unavailable response as json
    if test_limit(interval, limit, limit_single_client) == True:
        response = {'status': 'unavailable', 'limit_exceeded': 'True', 'retry-after':f'{interval}', 'http_code': '429 Too Many Requests'}
        return json.dumps(response)
    
    # returns false if limit not exceeded, send available/OK response as json
    else: 
        response = {'status': 'available', 'limit_exceeded': 'False', 'retry-after':'0', 'http_code': '200 OK'}
        return json.dumps(response)


# time3 endpoint - test 3, same limits as time1
# rates and limits set with globals
# integrated status check by adding '?status=check' to URL
@app.route('/time3/', methods=['GET'])
def time3():
    
    # pass 'status=check' in url args to test this endpoint's status
    if request.args and request.args['status'] == 'check':
        
        if test_limit(global_interval, global_limit, global_limit_single_client) == True:
            response = {'status': 'unavailable', 'limit_exceeded': 'True', 'retry-after':f'{global_interval}', 'http_code': '429 Too Many Requests'}
            return json.dumps(response)
    
        # returns false if limit not exceeded, send available/OK response as json
        else: 
            response = {'status': 'available', 'limit_exceeded': 'False', 'retry-after':'0', 'http_code': '200 OK'}
            return json.dumps(response)

    else:

        # check if limits have been exceeded
        request_check = process_request(request.headers, global_interval, global_limit, global_limit_single_client)
        
        # request check will abort request automatically if limit exceeded, or return True if OK to serve request
        if request_check == True:

            # call time function to create response
            json_response = time_json()

            # log the completed request in the db
            write_row(request.headers)

            # return the response
            return json_response


# time4 endpoint - cheating with Flask-Limiter
@app.route('/time4/', methods=['GET'])
@limiter.limit("3 per minute")
def time4():

    # call time function to create response
    json_response = time_json()

    # return the response
    return json_response


#~ testing endpoints

# analyze request headers endpoint - returns all Flask request object header info to screen
@app.route('/headers/', methods=['GET'])
def headers():
    
    return str(request.headers)


# simple time endpoint, doesn't write to db, not rate-limited, returns time json to screen
@app.route('/time_test/', methods=['GET'])
def time_test():

    # call time function to create response
    json_response = time_json()

    # return the response
    return json_response


# db test endpoint, writes a test request row to db, returns request headers to screen
@app.route('/db_test/', methods=['GET'])
def db_test():
    
    # log the test request in the db
    write_row(request.headers)
    
    # print the request headers to screen
    return str(request.headers)
