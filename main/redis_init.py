import os
import redis

redis_conn = redis.Redis(host=os.environ.get('REDIS_HOST'), port=int(os.environ.get('REDIS_PORT')), db=0)
