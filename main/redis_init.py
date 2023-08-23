import os
import redis

redis_conn = redis.Redis(host=os.environ.get('REDIS_HOST'), port=int(os.environ.get('REDIS_PORT')), db=int(os.environ.get('REDIS_DB')))

GLOBAL_TOKEN_LIMIT_PER_MINUTE = 90000
# Define the Lua script
lua_script = f"""
-- Get the current timestamp from Redis TIME command
local redis_time = redis.call('TIME')
local now = redis_time[1] + redis_time[2]/1000000

-- If update is true, attempt to add the new tokens to Redis
if ARGV[1] == 'true' and tonumber(ARGV[2]) > 0 then
  -- Generate a unique member by appending the current timestamp to the token count
  local member = tostring(ARGV[2]) .. ":" .. tostring(now)
  redis.call("ZADD", "tokens", now, member)
end

-- Remove tokens older than 60 seconds
redis.call("ZREMRANGEBYSCORE", "tokens", "-inf", now - 60)

-- Get all tokens in the last 60 seconds
local tokens = redis.call("ZRANGE", "tokens", 0, -1)
local token_count = 0
for _, token in ipairs(tokens) do
  -- Extract the token count from the member string
  local token_value = tonumber(string.match(token, "^(%d+):"))
  token_count = token_count + token_value
end

local limit = {GLOBAL_TOKEN_LIMIT_PER_MINUTE}
-- If token count is within the limit, return 0
if token_count <= limit then
  return 0
end

-- Calculate the delay using exponential backoff with jitter
local tokens_over_limit = token_count - limit
local delay_factor = math.ceil(tokens_over_limit / limit)
local delay = math.random() * math.pow(2, delay_factor)

-- Cap the delay at a maximum value
local max_delay = 60
delay = math.min(delay, max_delay)

return delay
"""

# Register the Lua script
lua_script = redis_conn.register_script(lua_script)
