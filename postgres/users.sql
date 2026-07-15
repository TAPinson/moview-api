create table users (
    id integer generated always as identity primary key,
    username varchar not null unique,
    email varchar not null unique,
    admin boolean not null default false,
    first_name varchar,
    last_name varchar
  );