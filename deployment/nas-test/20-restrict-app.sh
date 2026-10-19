#!/bin/bash
# Runs only on this preview volume's first MySQL initialization.
docker_process_sql <<'SQL'
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'nas_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE, SHOW VIEW ON `lu_test_nas_preview`.* TO 'nas_app'@'%';
ALTER USER 'nas_app'@'%' REQUIRE SSL;
SQL
