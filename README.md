# HouseCanary Rate Limiter Take-Home

This repo contains all the Docker stuff and other files, but the entire application is located in: `data/web/app.py`

It's running in Docker on a t3a.medium ec2 instance with NGINX and Gunicorn to manage networking, with the instance DNS pointed at https://housecanary/mansard.net. 

I used Python and Flask to serve requests, and MySQL as the database. When a request is made to an endpoint, its headers are passed to `process_request()` along with the information about the rate limits to be imposed on that endpoint:

```python
def process_request(request_headers, interval, limit, limit_single_client):
```

`process_request()` fetches however many requests there were in the last `interval` milliseconds from MySQL and tests them to see if: 

  * the total number of requests exceeds the value of `limit`
  * the number of requests from the current requester's IP exceeds the value of `limit_single_client`

If either condition is true, the endpoint returns a `429 Too Many Requests` error with additional information about which condition applies, and a `retry-after` header with the suggested interval to wait.

If neither condition is true, the request is logged to the database and the API returns a JSON package with the current time and some additional information: 

```json
{"iso_time_stamp": "2022-03-05T00:37:43.157272-05:00", "friendly_time": "Saturday March 05 2022, 12:37:43 AM EST", "uid": "03c29951-8852-45b7-929e-a02072b0d062"}
```


The endpoints available are noted and explained below.



# Endpoints

### https://housecanary.mansard.net/time1

This endpoint returns a JSON time package. Requests are limited to 6 per minute globally, and 3 per minute per IP.

### https://housecanary.mansard.net/time1_status
This endpoint returns a JSON package with information about the current limit status of the `time1` endpoint. 

Examples:
```json
{"status": "available", "limit_exceeded": "False", "retry-after": "0", "http_code": "200 OK"}

{"status": "unavailable", "limit_exceeded": "True", "retry-after": "60000", "http_code": "429 Too Many Requests"}
```

### https://housecanary.mansard.net/time2

Identical to `time1`, but with different limits. Requests are limited to 20 per 2 minutes globally, and 10 per 2 minutes per IP.

### https://housecanary.mansard.net/time2_status
Identical to `time1_status`

### https://housecanary.mansard.net/time3

Identical results and limits as `time1`, but using limits and intervals set with global variables and different logic.

### https://housecanary.mansard.net/time3?status=check
Identical to `time1_status`, but served from the same route/function and using the same globals.

### https://housecanary.mansard.net/time4
Identical results and limits as `time1`, but cheating by using the Flask-Limiter package, just as an example of what I'd probably REALLY do in a production scenario.

## Other Endpoints, for fun

### https://housecanary.mansard.net/headers
Returns the Flask request headers from your request

### https://housecanary.mansard.net/time_test
Just returns the time JSON package, no limit or database entry 

### https://housecanary.mansard.net/db_test
Creates a new database entry matching your request - returns your request headers. Will count against your quota in other endpoints!

# Other Thoughts

As mentioned in `time4`, in a production environment I'd rely on something well-developed and more robust than this, of course. MySQL as a db won't scale up well to high traffic, I'd have used Redis if I knew it slightly better. There are probably better ways to filter clients than IP, using sessions or cookies, or an API key that could have rate-limit information associated with it in another database table, etc. 
