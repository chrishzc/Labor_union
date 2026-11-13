#!/bin/sh
set -eu
umask 077
mkdir -p /run/registration
intake_hash=$(sha256sum /run/secrets/registration_intake_password | cut -d ' ' -f 1)
admin_hash=$(sha256sum /run/secrets/registration_admin_password | cut -d ' ' -f 1)
# Files contain password bytes without a trailing newline; hashes, never plaintext, enter ACL.
test -s /run/secrets/registration_intake_password
test -s /run/secrets/registration_admin_password
# Redis 7 replays Lua writes as MULTI/EXEC under the default ACL during AOF load.
# Keep that internal replay permission while disabling default-user authentication.
# See redis/redis#14541; unauthenticated clients must still fail the engine test.
cat > /run/registration/users.acl <<EOF
user default off resetpass +@all ~* &*
user registration-intake on #${intake_hash} -@all +ping +get +set +incr +zadd +pexpireat +eval +exists %RW~registration:ready %RW~registration:counter %RW~registration:submission:* %RW~registration:active:* %RW~registration:content:* %RW~registration:meta:* %RW~registration:passbook:meta:* %RW~registration:passbook:data:* %RW~registration:pending %RW~registration:deadlines %R~registration:result:*
user registration-admin on #${admin_hash} -@all +ping +get +set +incr +zadd +zrem +zrange +zrangebyscore +persist +del +exists +eval +dbsize +info +bgrewriteaof %RW~registration:*
EOF
chown -R redis:redis /run/registration
exec /usr/local/bin/docker-entrypoint.sh redis-server /usr/local/etc/redis/redis.conf
