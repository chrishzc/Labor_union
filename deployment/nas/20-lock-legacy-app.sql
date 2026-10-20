-- New runtime identities are installed by the one-shot security configurator.
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'nas_app'@'%';
ALTER USER 'nas_app'@'%' REQUIRE SSL ACCOUNT LOCK;
