-- lua/allow_callback.lua : check three limits, then count, atomically
-- KEYS[1]=rl:cb:{phone}:10m  KEYS[2]=rl:cb:{phone}:day  KEYS[3]=budget:calls:{date}
-- ARGV[1]=limit_10m  ARGV[2]=limit_day  ARGV[3]=daily_budget
-- returns 1 = allowed, 0 = per-number limit hit, -1 = global budget hit
local a = tonumber(redis.call('GET', KEYS[1]) or '0')
local b = tonumber(redis.call('GET', KEYS[2]) or '0')
local c = tonumber(redis.call('GET', KEYS[3]) or '0')
if c >= tonumber(ARGV[3]) then return -1 end
if a >= tonumber(ARGV[1]) or b >= tonumber(ARGV[2]) then return 0 end
if redis.call('INCR', KEYS[1]) == 1 then redis.call('EXPIRE', KEYS[1], 600) end
if redis.call('INCR', KEYS[2]) == 1 then redis.call('EXPIRE', KEYS[2], 86400) end
if redis.call('INCR', KEYS[3]) == 1 then redis.call('EXPIRE', KEYS[3], 172800) end
return 1
