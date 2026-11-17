create table movies (
  id integer primary key check (id > 0),
  poster_path text,
  adult boolean,
  overview text,
  release_date date,
  genre_ids integer[] not null default '{}',
  original_title text,
  original_language text,
  title text,
  backdrop_path text,
  popularity double precision,
  vote_count integer,
  video boolean,
  vote_average double precision,
  updated_at timestamptz not null default now()
);