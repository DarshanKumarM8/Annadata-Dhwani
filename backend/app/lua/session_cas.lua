-- lua/session_cas.lua : atomic compare-and-set of the session
-- KEYS[1]=sess:{phone}   ARGV[1]=expected_version  ARGV[2]=new_json  ARGV[3]=ttl_seconds
-- returns 1 = written, 0 = version mismatch (concurrent or stale handler), -1 = session missing
local cur = redis.call('GET', KEYS[1])
if not cur then
  if ARGV[1] ~= '0' then return -1 end
else
  if tostring(cjson.decode(cur).version) ~= ARGV[1] then return 0 end
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', tonumber(ARGV[3]))
return 1
