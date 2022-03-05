-- MySQL db create procedure
-- just an example to show the structure of the db

CREATE DATABASE `housecanary`;
USE `housecanary`;

CREATE TABLE `traffic` (
  `uid` varchar(36) NOT NULL,
  `requester` varchar(16) NOT NULL,
  `request_time` datetime(3) DEFAULT CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
