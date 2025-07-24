# SQL

CREATE DATABASE IF NOT EXISTS testdb;

USE testdb;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (name, email) VALUES
('Alice', 'alice@example.com'),
('Bob', 'bob@example.com'),
('test', 'test@test.com');

CREATE TABLE event_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(255),
    executed_at DATETIME DEFAULT NOW(),
    message TEXT
);

SET GLOBAL event_scheduler = ON;

DELIMITER //

CREATE EVENT IF NOT EXISTS purge_logs
ON SCHEDULE EVERY 3 MINUTE
DO
BEGIN
    DELETE FROM users WHERE created_at < NOW() - INTERVAL 30 SECOND;

    INSERT INTO event_log (event_name, message)
    VALUES ('purge_logs', 'Successfully purged logs older.');

    INSERT INTO users (name, email) 
    VALUES ('xxx', 'xxx@example.com');
END;
//

DELIMITER ;

---

SELECT 
    EVENT_NAME,
    STATUS,
    LAST_EXECUTED,
    INTERVAL_VALUE,
    INTERVAL_FIELD
FROM 
    information_schema.EVENTS
WHERE 
    EVENT_SCHEMA = 'testdb';

SHOW VARIABLES LIKE 'event_scheduler';
SHOW PROCESSLIST;
select * from event_log;

---

docker run -d \
  --name mariadb \
  -v $(pwd)/my.cnf:/etc/mysql/my.cnf:ro \
  -v $(pwd)/init.sql:/docker-entrypoint-initdb.d/init.sql:ro \
  -e MARIADB_ROOT_PASSWORD=root \
  -p 3306:3306 \
  mariadb:11 \
  --defaults-file=/etc/mysql/my.cnf
  
docker run -d \
  --name mariadb \
  -v $(pwd)/init.sql:/docker-entrypoint-initdb.d/init.sql:ro \
  -e MARIADB_ROOT_PASSWORD=root \
  -p 3306:3306 \
  mariadb:11

docker exec -it mariadb /bin/bash
