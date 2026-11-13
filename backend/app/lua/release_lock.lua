-- lua/release_lock.lua : delete the lock only if we still own it
-- KEYS[1]=lock:call:{phone}  ARGV[1]=token
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
